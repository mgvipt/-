import hashlib, hmac, json, secrets, time, uuid
from django.test import TestCase, override_settings
from apps.accounts.models import User
from apps.crm.models import Contact, Deal
from apps.inbox.models import Channel, Conversation, Message
from .models import Instruction, InstructionEvent, ConsentEvent, GuideRequest
from .services import receive_guide, receive_event, IdentityConflict, prepare_share, record_shared

@override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}},SHOP_WEBHOOK_SECRET='test-secret')
class ContentLibraryTests(TestCase):
    def setUp(self):
        self.i=Instruction.objects.create(slug='microcement',title='Техкарта',status='published',content={'steps':[]})
        self.body={'submission_id':'request-123456','lead_magnet_slug':'microcement','name':'Тест','phone':'067 000 00 31','email':'TEST@example.test','marketing_consent':False,'guide_token':secrets.token_hex(32),'visitor_id':secrets.token_hex(32),'source_platform':'website'}
    def test_dedup_and_retry_without_deal(self):
        r,dup=receive_guide(self.body);self.assertFalse(dup)
        self.assertEqual(r.profile.contact.phone,'+380670000031');self.assertEqual(r.profile.contact.email,'test@example.test')
        again,dup=receive_guide(self.body);self.assertTrue(dup);self.assertEqual(r.pk,again.pk)
        second,_=receive_guide({**self.body,'submission_id':'request-second','phone':'+380670000031','guide_token':secrets.token_hex(32)})
        self.assertEqual(r.profile_id,second.profile_id);self.assertEqual(Contact.objects.count(),1);self.assertEqual(Deal.objects.count(),0)
    def test_email_only_conflict_and_validation(self):
        r,_=receive_guide({**self.body,'phone':''});self.assertEqual(r.profile.contact.email,'test@example.test')
        Contact.objects.create(first_name='Other',phone='+380670000031')
        with self.assertRaises(IdentityConflict):receive_guide({**self.body,'submission_id':'conflict-1234'})
        with self.assertRaises(ValueError):receive_guide({**self.body,'phone':'','email':''})
        self.assertEqual(GuideRequest.objects.count(),1)
    def test_same_key_changed_data_rejected(self):
        receive_guide(self.body)
        with self.assertRaises(IdentityConflict):receive_guide({**self.body,'name':'Інше'})
    def test_consent_optional_omission_not_revocation(self):
        r,_=receive_guide({**self.body,'marketing_consent':True})
        receive_guide({**self.body,'submission_id':'request-next','guide_token':secrets.token_hex(32)})
        r.profile.refresh_from_db();self.assertTrue(r.profile.marketing_consent);self.assertEqual(ConsentEvent.objects.count(),1)
    def test_anonymous_events_linked_once(self):
        event={'event_id':str(uuid.uuid4()),'lead_magnet_slug':'microcement','event':'article_view','visitor_id':self.body['visitor_id']}
        e,_=receive_event(event);receive_event(event);self.assertIsNone(e.profile_id)
        r,_=receive_guide(self.body);e.refresh_from_db();self.assertEqual(e.profile_id,r.profile_id)
        self.assertEqual(InstructionEvent.objects.filter(name='article_view').count(),1)
    def test_public_guide_no_pdf_and_published_only(self):
        r=self.client.get('/instructions/microcement/?r=invalid');self.assertEqual(r.status_code,200)
        self.assertNotContains(r,'Завантажити PDF');self.assertContains(r,'AI-візуалізація')
        self.assertEqual(self.client.get('/instructions/missing/').status_code,404)
        self.assertEqual(self.client.get('/api/content-library/public/microcement/').status_code,200)
    def test_signed_webhook(self):
        body=json.dumps({**self.body,'form':'lead_magnet'}).encode();ts=str(int(time.time()))
        self.assertEqual(self.client.post('/api/integrations/shop/leads/',body,content_type='application/json').status_code,403)
        sig=hmac.new(b'test-secret',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        r=self.client.post('/api/integrations/shop/leads/',body,content_type='application/json',HTTP_X_WALLCOV_TIMESTAMP=ts,HTTP_X_WALLCOV_SIGNATURE=sig)
        self.assertEqual(r.status_code,201,r.content)
    def test_dashboard_empty_and_populated(self):
        user=User.objects.create_user(username='content-owner',is_superuser=True);self.client.force_login(user)
        r=self.client.get('/api/content-library/audience/');self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['total'],0)
        receive_guide(self.body)
        r=self.client.get('/api/content-library/audience/?instruction=microcement');self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['total'],1)
        self.client.logout();self.assertIn(self.client.get('/api/content-library/audience/').status_code,[401,403])
    def test_insert_not_counted_send_once(self):
        user=User.objects.create_user(username='manager',is_superuser=True)
        channel=Channel.objects.create(name='Isolated test',kind='telegram')
        conv=Conversation.objects.create(channel=channel,external_chat_id='test-content-only')
        share,text=prepare_share('microcement',conv,user)
        self.assertEqual(InstructionEvent.objects.filter(name='instruction_shared').count(),0)
        msg=Message.objects.create(conversation=conv,direction='out',text=text,status='sent')
        record_shared(msg,conv,user);record_shared(msg,conv,user)
        self.assertEqual(InstructionEvent.objects.filter(name='instruction_shared').count(),1)
