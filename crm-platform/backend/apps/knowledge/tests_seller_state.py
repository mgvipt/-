from django.test import TestCase
from unittest.mock import patch
from apps.crm.models import Contact, Deal, DealItem, Funnel, Stage, Payment
from apps.inbox.models import Channel, Conversation, Message
from .seller_state import refresh, KEY, active_order, action_blocked

class SellerStateTests(TestCase):
    def setUp(self):
        self.contact=Contact.objects.create(first_name='Test')
        self.channel=Channel.objects.create(name='Test',kind='instagram',config={'ai_reply':True,'ai_reply_after_handoff':True})
        self.conv=Conversation.objects.create(channel=self.channel,contact=self.contact,external_chat_id='test',config={'unrelated':'keep'})
    def say(self,text,direction='in'):
        return Message.objects.create(conversation=self.conv,text=text,direction=direction)
    def test_selection_survives_many_messages_and_agent_adverts(self):
        first=self.say('Обираю Галатею. Колір MSK14/08, без дощечки')
        refresh(self.conv,first)
        for i in range(30):self.say('Пропонуємо Луну',direction='out')
        last=self.say('Скільки коштує?')
        s=refresh(self.conv,last)
        self.assertEqual(s['fields']['material']['value']['product_id'],1623)
        self.assertEqual(s['fields']['color']['value'],'MSK14/08')
        self.assertFalse(s['fields']['board']['value'])
        self.conv.refresh_from_db();self.assertEqual(self.conv.config['unrelated'],'keep')
    def test_question_does_not_replace_choice(self):
        refresh(self.conv,self.say('Обираю Галатею'))
        s=refresh(self.conv,self.say('А якщо обираю Луну?'))
        self.assertEqual(s['fields']['material']['value']['product_id'],1623)
    def test_explicit_change_replaces_choice(self):
        refresh(self.conv,self.say('Обираю Галатею'))
        s=refresh(self.conv,self.say('Обираю Луну'))
        self.assertEqual(s['fields']['material']['value']['product_id'],1649)
    def test_new_project_clears_previous_selection(self):
        refresh(self.conv,self.say('Обираю Галатею'))
        s=refresh(self.conv,self.say('Це новий будинок'))
        self.assertEqual(s['fields'],{})
    def test_floor_area_not_wall_area(self):
        s=refresh(self.conv,self.say('Площа підлоги 12 м2, висота 2,5 м'))
        self.assertNotIn('wall_area_m2',s['fields'])
        s=refresh(self.conv,self.say('Площа стін 20 м2'))
        self.assertEqual(s['fields']['wall_area_m2']['value'],'20')
    def test_historical_preview_not_future_and_no_rollback(self):
        old=self.say('Обираю Галатею');new=self.say('Обираю Луну');refresh(self.conv,new)
        self.assertEqual(refresh(self.conv,old)['fields']['material']['value']['product_id'],1623)
        self.conv.refresh_from_db();self.assertEqual(self.conv.config[KEY]['through_id'],new.pk)
    def test_distinct_conversation_not_shared(self):
        refresh(self.conv,self.say('Обираю Галатею'))
        other=Conversation.objects.create(channel=self.channel,contact=self.contact,external_chat_id='other')
        m=Message.objects.create(conversation=other,text='Вітаю',direction='in')
        self.assertEqual(refresh(other,m)['fields'],{})
    def make_deal(self):
        f=Funnel.objects.create(name='Test');st=Stage.objects.create(funnel=f,name='New')
        d=Deal.objects.create(contact=self.contact,funnel=f,stage=st,amount=430)
        DealItem.objects.create(deal=d,custom_name='test',quantity=1,price=430)
        return d
    def test_ambiguous_orders_block_action(self):
        self.make_deal();self.make_deal();self.assertTrue(active_order(self.conv)[1]);self.assertTrue(action_blocked(self.conv))
    def test_paid_order_blocks_repeat_order(self):
        d=self.make_deal();Payment.objects.create(deal=d,provider='manual',amount=100,is_paid=True)
        self.assertTrue(action_blocked(self.conv))
    def test_web_does_not_use_contact_orders(self):
        self.make_deal();self.channel.kind='web';self.channel.save()
        self.assertEqual(active_order(self.conv),(None,False))
    def test_acceptance_test_blocks_financial_actions(self):
        self.conv.config['seller_acceptance_test']=True
        self.assertTrue(action_blocked(self.conv))
    def test_external_owned_comment_sends_nothing(self):
        from apps.inbox.comment_reply import maybe_send
        with patch('apps.inbox.meta.private_reply') as send:
            self.assertFalse(maybe_send(self.conv,'testcomment','Галатея'))
            send.assert_not_called()

    def test_short_area_correction_updates_persisted_value(self):
        refresh(self.conv,self.say('Площа стін 20 м2'))
        s=refresh(self.conv,self.say('тепер 10 м2'))
        self.assertEqual(s['fields']['wall_area_m2']['value'],'10')

    def test_bound_order_does_not_bypass_ambiguity(self):
        a=self.make_deal();self.make_deal();self.conv.config['seller_order_id']=a.pk
        self.assertTrue(action_blocked(self.conv))

    def test_paid_guard_applies_at_financial_helper_entry(self):
        from apps.inbox.ai_reply import _make_kit_offer, _make_volume_offer, _maybe_volume_doc, _maybe_requisites
        d=self.make_deal();Payment.objects.create(deal=d,provider='manual',amount=1,is_paid=True)
        m=self.say('Дайте реквізити')
        with patch('apps.crm.views.make_offer') as offer, patch('apps.crm.views.send_requisites') as requisites:
            _make_kit_offer(self.conv,{'product':'test'})
            _make_volume_offer(self.conv,{'ok':True},{})
            _maybe_volume_doc(self.conv,{'ok':True},None)
            _maybe_requisites(self.conv,m)
            offer.assert_not_called();requisites.assert_not_called()

    def test_switch_preserves_other_items(self):
        from apps.inbox.ai_reply import _switch_kit
        d=self.make_deal();DealItem.objects.create(deal=d,custom_name='Brush',quantity=1,price=100)
        with patch('apps.crm.views.make_offer') as offer:
            self.assertFalse(_switch_kit(self.conv,self.say('без дощечки')))
            offer.assert_not_called()
        self.assertEqual(d.items.count(),2)

    def test_quote_includes_undercoat_and_separates_deep_primer(self):
        from apps.warehouse.models import Product
        from .volume_calc import for_dialog,prompt_block
        for pid,name,price,cons in [(1623,'Galateya','100','0.2'),(1583,'Second Layer','200','0.3'),(1927,'Primer Deep','80','0.17')]:
            Product.objects.create(pk=pid,name=name,price=price,unit='кг',consumption_per_m2=cons)
        c=for_dialog([{'role':'client','text':'Галатея на 10 м2'}])
        self.assertEqual({x['product_id'] for x in c['lines']},{1623,1583})
        self.assertEqual(c['optional_deep'][0]['product_id'],1927)
        self.assertNotIn('МОЖНА ПРИБРАТИ',prompt_block(c))

    def test_negative_color_is_not_a_selection(self):
        s=refresh(self.conv,self.say('не беру MSK14/08'))
        self.assertNotIn('color',s['fields'])

    def test_negative_primer_request_never_adds_paid_item(self):
        from .volume_calc import for_dialog
        with patch('apps.knowledge.volume_calc.estimate',return_value={'lines':[]}),patch('apps.knowledge.volume_calc.find_color',return_value=None),patch('apps.knowledge.volume_calc.tint_estimate',return_value=None):
            from . import volume_calc
            for_dialog([{'role':'client','text':'Галатея на 10 м2'},{'role':'client','text':'Додати глибокий ґрунт не потрібно, він у мене є'}])
            self.assertFalse(volume_calc.estimate.call_args_list[0].kwargs['include_deep'])
