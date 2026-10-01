from decimal import Decimal
from django.test import TestCase
from apps.crm.models import Contact, Deal, DealItem, Funnel, Stage, Payment
from apps.inbox.models import Channel, Conversation, Message
from .conversation_context import snapshot, prompt_block

class ConversationEvidenceTests(TestCase):
    def setUp(self):
        self.contact=Contact.objects.create(first_name='Test')
        self.ch=Channel.objects.create(name='Test',kind='instagram')
        self.conv=Conversation.objects.create(channel=self.ch,contact=self.contact,external_chat_id='test')
        f=Funnel.objects.create(name='Test');st=Stage.objects.create(funnel=f,name='New')
        self.deal=Deal.objects.create(contact=self.contact,funnel=f,stage=st,amount=430)
        DealItem.objects.create(deal=self.deal,custom_name='Galateya test',quantity=1,price=430)
        self.incoming=Message.objects.create(conversation=self.conv,direction='in',text='Де моє замовлення?')

    def test_payment_is_current_database_fact_not_chat_promise(self):
        r=snapshot(self.conv,self.incoming)
        self.assertFalse(r['orders'][0]['fully_paid'])
        Payment.objects.create(deal=self.deal,provider='manual',amount=430,is_paid=True)
        r=snapshot(self.conv,self.incoming)
        self.assertTrue(r['orders'][0]['fully_paid'])
        self.assertEqual(r['orders'][0]['quoted_total'],'430.00 грн')

    def test_other_contact_orders_are_not_exposed(self):
        other=Contact.objects.create(first_name='Other')
        Deal.objects.create(contact=other,funnel=self.deal.funnel,stage=self.deal.stage,amount=999)
        self.assertEqual(len(snapshot(self.conv,self.incoming)['orders']),1)

    def test_selected_color_survives_recent_twenty_messages(self):
        old=Message.objects.create(conversation=self.conv,direction='in',text='Обрала колір MSK14/08 з дощечкою')
        for i in range(25):
            last=Message.objects.create(conversation=self.conv,direction='in',text='Дякую')
        r=snapshot(self.conv,last)
        evidence=next(x for x in r['earlier_evidence'] if x['message_id']==old.pk)
        self.assertIn('MSK14/08',evidence['mentioned_color_codes'])

    def test_images_are_not_claimed_as_read_and_failed_send_is_marked(self):
        photo=Message.objects.create(conversation=self.conv,direction='out',text='Фото',status='failed',attachments=[{'type':'image','name':'Galateya','color_code':'MSK14/08'},{'type':'send_error'}])
        last=Message.objects.create(conversation=self.conv,direction='in',text='Не бачу фото')
        e=next(x for x in snapshot(self.conv,last)['earlier_evidence'] if x['message_id']==photo.pk)
        self.assertTrue(e['delivery_failed'])
        self.assertFalse(e['attachments'][0]['pixels_read'])

    def test_no_future_message_leaks_into_reply(self):
        later=Message.objects.create(conversation=self.conv,direction='in',text='Колір 19-8')
        self.assertNotIn(later.pk,[x['message_id'] for x in snapshot(self.conv,self.incoming)['earlier_evidence']])

    def test_phone_number_is_not_placed_in_prompt(self):
        self.contact.phone='+380501234567';self.contact.save()
        p=prompt_block(self.conv,self.incoming)
        self.assertNotIn(self.contact.phone,p)
        self.assertIn('"contact_phone_present": true',p)

    def test_anonymous_webchat_cannot_read_orders_by_entered_contact_phone(self):
        self.contact.phone='+380501234567';self.contact.save()
        web=Channel.objects.create(name='Web',kind='web')
        conv=Conversation.objects.create(channel=web,contact=self.contact,external_chat_id='new-unverified-session')
        msg=Message.objects.create(conversation=conv,direction='in',text='Мої замовлення?')
        result=snapshot(conv,msg)
        self.assertEqual(result['orders'],[])
        self.assertFalse(result['contact_phone_present'])

    def test_standalone_fractional_color_survives_newer_promotions(self):
        old=Message.objects.create(conversation=self.conv,direction='in',text='MSK10-0,1')
        for i in range(25):
            last=Message.objects.create(conversation=self.conv,direction='out',text='Обрати колір і оплатити')
        rows=snapshot(self.conv,last)['earlier_evidence']
        evidence=next(x for x in rows if x['message_id']==old.pk)
        self.assertEqual(evidence['mentioned_color_codes'],['MSK10-0,1'])
