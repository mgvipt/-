from unittest.mock import patch
from types import SimpleNamespace
from django.test import TestCase
from django.core import signing
from apps.inbox.models import Channel,Conversation,Message
from apps.crm.models import Deal,Payment
from .seller_simulation import run,SALT
from .seller_state import reduce_message
from .seller_decision import decide,volume_invoice_lines

class SellerSimulationTests(TestCase):
    def setUp(self):
        self.channel=Channel.objects.create(name='Instagram test',kind='instagram',config={'ai_reply':True})
    def data(self,**kw):
        return dict(channel_id=self.channel.pk,text='Скільки коштує?',**kw)
    @patch('apps.knowledge.seller_simulation.decide')
    def test_no_live_entities_and_signed_history(self,decision):
        decision.return_value=({'text':'Вітаю','cost':{'usd':0,'model':'test','in_tok':0,'out_tok':0}},None)
        before=(Conversation.objects.count(),Message.objects.count(),Deal.objects.count(),Payment.objects.count())
        r=run(self.data(),1)
        self.assertEqual(before,(Conversation.objects.count(),Message.objects.count(),Deal.objects.count(),Payment.objects.count()))
        s=signing.loads(r['simulation_token'],salt=SALT)
        self.assertEqual(len(s['messages']),2)
        run(self.data(simulation_token=r['simulation_token']),1)
        self.assertEqual(len(decision.call_args.args[0]),3)
        with self.assertRaises(ValueError):run(self.data(simulation_token=r['simulation_token']),2)
        with self.assertRaises(ValueError):run(self.data(simulation_token=r['simulation_token']+'broken'),1)
    def test_new_object_overwrites_old_area(self):
        s={'fields':{}}
        for i,t in enumerate(['Це новий проект. Обираю Галатею. Площа стін 20 м2','Це інший об’єкт: Галатея на 10 м², колір MSK20-3, глибокий ґрунт у мене є. Покажи повний розрахунок'],1):
            reduce_message(s,SimpleNamespace(text=t,pk=i,direction='in',attachments=[]))
        self.assertEqual(s['project_start_id'],2)
        self.assertEqual(s['fields']['wall_area_m2']['value'],'10')
        self.assertEqual(s['fields']['color']['value'],'MSK20-3')
    @patch('apps.knowledge.seller_decision.answer')
    @patch('apps.knowledge.seller_decision.final_quote_reply',return_value=None)
    @patch('apps.knowledge.seller_decision.for_dialog',return_value=None)
    def test_shared_route_approved_and_no_override(self,calc,quote,answer):
        answer.return_value={'text':'ok'}
        decide([{'role':'client','text':'питання'}],{'fields':{}},'питання')
        self.assertEqual(answer.call_args.args[0],'yulia_web')
        self.assertFalse(answer.call_args.kwargs['include_drafts'])
    def test_invoice_has_tint_before_total(self):
        calc={'ok':True,'lines':[{'product_id':1,'qty':2,'price':100}], 'tara_lines':[{'product_id':2,'qty':1,'price':30}], 'tint':{'total':50}}
        lines=volume_invoice_lines(calc,{'tint':True})
        self.assertEqual(sum(x['qty']*x['price'] for x in lines),280)
        calc['tint']={'need_color':True}
        self.assertIsNone(volume_invoice_lines(calc,{'tint':True}))
    @patch('apps.knowledge.seller_simulation.decide')
    @patch('apps.knowledge.volume_calc.shown_to_client',return_value=True)
    def test_invoice_signed_state_serializable_and_no_writes(self,shown,decision):
        from decimal import Decimal
        calc={'ok':True,'area':10,'color':'MSK20-3','lines':[{'product_id':1623,'qty':Decimal('1.5'),'price':Decimal('1330')}],
              'tara_lines':[],'tint':{'total':Decimal('452')}}
        decision.return_value=({'text':'Оформлю','order':{'volume':True},'intent':'confirm_order'},calc)
        r=run(self.data(),1)
        self.assertEqual(r['simulation']['invoice']['total'],2447)
        self.assertEqual(len(signing.loads(r['simulation_token'],salt=SALT)['orders']),1)
        self.assertEqual(Deal.objects.count(),0)
    def test_runtime_api_owner_only(self):
        from apps.accounts.models import User
        from rest_framework.test import APIClient
        owner=User.objects.create_superuser(username='sim-owner',password='x')
        c=APIClient();c.force_authenticate(owner)
        with patch('apps.knowledge.seller_simulation.decide',return_value=({'text':'ok'},None)):
            r=c.post('/api/knowledge/test-chat/',dict(runtime_seller=True,**self.data()),format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertIn('simulation_token',r.data)
        c.force_authenticate(None)
        self.assertIn(c.post('/api/knowledge/test-chat/',dict(runtime_seller=True,**self.data()),format='json').status_code,(401,403))
