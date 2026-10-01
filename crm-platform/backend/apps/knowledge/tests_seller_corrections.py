from unittest.mock import patch
from django.test import TestCase
from apps.crm.models import Contact
from .answer import answer
from .seller_prompt import system_for

class CallbackPhoneTests(TestCase):
    def run_callback(self,text='Передзвоніть мені',contact_id=None,messages=None):
        with patch('apps.knowledge.answer.call_claude') as llm:
            result=answer('yulia_web',messages or [{'role':'client','text':text}],contact_id=contact_id)
        llm.assert_not_called()
        return result

    def test_phone_in_card_not_requested_again(self):
        c=Contact.objects.create(first_name='Test',phone='+380501234567')
        r=self.run_callback(contact_id=c.pk)
        self.assertTrue(r['extra']['callback_phone_available'])
        self.assertNotIn('Напишіть',r['text'])
        self.assertNotIn(c.phone,r['text'])

    def test_missing_phone_requests_it(self):
        c=Contact.objects.create(first_name='Test',phone='')
        self.assertIn('номер телефону',self.run_callback(contact_id=c.pk)['text'])
        self.assertFalse(self.run_callback(contact_id=c.pk)['extra']['callback_phone_available'])

    def test_current_card_is_read_every_time(self):
        c=Contact.objects.create(first_name='Test',phone='')
        self.assertFalse(self.run_callback(contact_id=c.pk)['extra']['callback_phone_available'])
        Contact.objects.filter(pk=c.pk).update(phone='+380501234567')
        self.assertTrue(self.run_callback(contact_id=c.pk)['extra']['callback_phone_available'])

    def test_phone_in_message_is_not_requested_again(self):
        self.assertTrue(self.run_callback(text='Передзвоніть +380 50 123 45 67')['extra']['callback_phone_available'])

    def test_another_contacts_phone_is_not_used(self):
        Contact.objects.create(first_name='Other',phone='+380501234567')
        self.assertFalse(self.run_callback()['extra']['callback_phone_available'])

    def test_russian_request(self):
        self.assertIn('Напишите',self.run_callback(text='Перезвоните мне')['text'])

    def test_testchat_without_contact_does_not_assume_phone(self):
        self.assertTrue(self.run_callback()['handoff'])
        self.assertEqual(self.run_callback()['cost']['usd'],0)

    def test_exterior_walls_and_floor_distinct(self):
        p=system_for('Instagram')
        self.assertIn('зокрема на СТІНАХ',p)
        self.assertIn('Для ПІДЛОГИ на вулиці не поспішай обіцяти',p)
