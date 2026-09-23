import hashlib, hmac, json, secrets, time, uuid
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from apps.accounts.models import User
from apps.crm.models import Contact, Deal
from apps.inbox.models import Channel, Conversation, Message
from .models import (Instruction, InstructionEvent, ConsentEvent, GuideRequest,
                     LeadForm, KeywordAutomation, KeywordAutomationRun, AudienceProfile)
from .services import receive_guide, receive_event, IdentityConflict, prepare_share, record_shared
from .keyword_automation import process_keyword_message

@override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}},SHOP_WEBHOOK_SECRET='test-secret')
class ContentLibraryTests(TestCase):
    def setUp(self):
        self.i=Instruction.objects.create(slug='microcement',title='Техкарта',status='published',content={'steps':[]})
        self.body={'submission_id':'request-123456','lead_magnet_slug':'microcement','name':'Тест','phone':'067 000 00 31','email':'TEST@example.test','preferred_channel':'whatsapp','marketing_consent':False,'guide_token':secrets.token_hex(32),'visitor_id':secrets.token_hex(32),'source_platform':'website'}
    def test_dedup_and_retry_without_deal(self):
        r,dup=receive_guide(self.body);self.assertFalse(dup)
        self.assertEqual(r.profile.contact.phone,'+380670000031');self.assertEqual(r.profile.contact.email,'test@example.test')
        self.assertEqual(r.profile.preferred_channel,'whatsapp')
        self.assertTrue(r.profile.identities.filter(kind='whatsapp',value='+380670000031',verified_at__isnull=True).exists())
        again,dup=receive_guide(self.body);self.assertTrue(dup);self.assertEqual(r.pk,again.pk)
        second,_=receive_guide({**self.body,'submission_id':'request-second','phone':'+380670000031','guide_token':secrets.token_hex(32)})
        self.assertEqual(r.profile_id,second.profile_id);self.assertEqual(Contact.objects.count(),1);self.assertEqual(Deal.objects.count(),0)
    def test_email_only_conflict_and_validation(self):
        r,_=receive_guide({**self.body,'phone':'','preferred_channel':'email'});self.assertEqual(r.profile.contact.email,'test@example.test')
        Contact.objects.create(first_name='Other',phone='+380670000031')
        with self.assertRaises(IdentityConflict):receive_guide({**self.body,'submission_id':'conflict-1234'})
        with self.assertRaises(ValueError):receive_guide({**self.body,'phone':'','email':''})
        with self.assertRaises(ValueError):receive_guide({**self.body,'submission_id':'bad-channel','preferred_channel':'sms'})
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
        self.assertNotContains(r,'Завантажити PDF');self.assertNotContains(r,'Друкувати чек-лист');self.assertContains(r,'AI-візуалізація')
        self.assertContains(r,'https://wallcov.com.ua/rozrakhunok?article=microcement-shower')
        user=User.objects.create_user(username='guide-manager',is_superuser=True);self.client.force_login(user)
        self.assertContains(self.client.get('/instructions/microcement/'),'Друкувати чек-лист')
        self.client.logout()
        self.assertEqual(self.client.get('/instructions/missing/').status_code,404)
        self.assertEqual(self.client.get('/api/content-library/public/microcement/').status_code,200)
    def test_signed_guide_contact_and_receipt_link(self):
        receipt,_=receive_guide(self.body)
        page=self.client.get('/instructions/microcement/?r='+receipt.token)
        self.assertContains(page,'r='+receipt.token)
        raw=json.dumps({'guide_token':receipt.token,'article':'microcement-shower'}).encode();ts=str(int(time.time()))
        self.assertEqual(self.client.post('/api/content-library/guide-contact/',raw,content_type='application/json').status_code,403)
        sig=hmac.new(b'test-secret',ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        csrf_client=Client(enforce_csrf_checks=True)
        response=csrf_client.post('/api/content-library/guide-contact/',raw,content_type='application/json',HTTP_X_WALLCOV_TIMESTAMP=ts,HTTP_X_WALLCOV_SIGNATURE=sig)
        self.assertEqual(response.status_code,200,response.content);self.assertEqual(response.json()['display_name'],'Тест')
        self.assertEqual(response.json()['preferred_channel'],'whatsapp')
    def test_editable_form_and_public_configuration(self):
        form=LeadForm.objects.create(slug='microcement',name='Форма',title='Заголовок',intro='Вступ',instruction=self.i,fields=['name','phone'],channels=['viber'],consent_text='Згода',submit_text='Відкрити')
        r=self.client.get('/api/content-library/forms/microcement/');self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['channels'],['viber'])
        user=User.objects.create_user(username='automation-owner',is_superuser=True);self.client.force_login(user)
        r=self.client.post('/api/content-library/automations/',data=json.dumps({'action':'save_form','id':form.id,'slug':'microcement','name':'Нова назва','title':'Новий заголовок','intro':'Текст','instruction_id':self.i.id,'fields':['name','phone','email'],'channels':['viber','whatsapp','telegram','email'],'consent_text':'Окрема згода','submit_text':'Отримати','enabled':True}),content_type='application/json')
        self.assertEqual(r.status_code,200,r.content);form.refresh_from_db();self.assertEqual(form.name,'Нова назва');self.assertNotIn('sms',form.channels)
    def test_reviewed_instruction_update_increments_version(self):
        dry=StringIO();call_command('publish_microcement',stdout=dry)
        self.assertIn('DRY_RUN: update instruction',dry.getvalue())
        out=StringIO();call_command('publish_microcement','--apply',stdout=out)
        self.i.refresh_from_db();self.assertEqual(self.i.version,2)
        titles=[step['title'] for step in self.i.content['steps']]
        self.assertEqual(titles[:3],['Primer Deep 1','Quartz Primer 2','Microcement FINE + сітка 2×2 мм'])
        self.assertNotIn('склохолст',' '.join(titles).lower())
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
        self.assertEqual(r.json()['contacts'][0]['preferred_channel'],'whatsapp')
        detail=self.client.get('/api/contacts/%d/' % r.json()['contacts'][0]['id'])
        self.assertEqual(detail.status_code,200,detail.content)
        self.assertEqual(detail.json()['content_subscription']['preferred_channel'],'whatsapp')
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
    def test_keyword_from_direct_and_comment_is_captured_without_crm_reply(self):
        form=LeadForm.objects.create(slug='microcement',name='Форма',title='Заголовок',instruction=self.i,fields=['name','phone'],channels=['viber'])
        rule=KeywordAutomation.objects.create(title='МІКРО',keywords=['МІКРО'],match_mode='exact',platforms=['instagram'],form=form,reply_text='Текст {form_url}',public_replies=['Відправили в Direct'],enabled=True)
        contact=Contact.objects.create(first_name='Client',nickname='@client')
        channel=Channel.objects.create(name='Meta · Instagram',kind='instagram')
        direct=Conversation.objects.create(channel=channel,external_chat_id='ig-1',contact=contact)
        msg=Message.objects.create(conversation=direct,direction='in',text='мікро')
        run=process_keyword_message(msg);self.assertEqual(run.status,'captured');self.assertEqual(direct.messages.filter(direction='out').count(),0)
        comment=Conversation.objects.create(channel=channel,external_chat_id='comment:instagram:post:client',contact=contact,config={'source_card':{'media_id':'post'}})
        cmsg=Message.objects.create(conversation=comment,direction='in',text='МІКРО')
        duplicate=process_keyword_message(cmsg);self.assertEqual(duplicate.status,'duplicate')
        self.assertEqual(AudienceProfile.objects.count(),1);self.assertEqual(InstructionEvent.objects.filter(name='keyword_triggered').count(),1)
    @patch('apps.content_library.chatplace_automation._mcp')
    def test_chatplace_sync_combines_comment_and_direct(self,mcp):
        from .chatplace_automation import sync_to_chatplace
        form=LeadForm.objects.create(slug='microcement',name='Форма',title='Заголовок',instruction=self.i,fields=['name','phone'],channels=['viber'])
        rule=KeywordAutomation.objects.create(title='МІКРО',keywords=['МІКРО'],match_mode='exact',platforms=['instagram'],form=form,reply_text='Техкарта готова.\n\n{form_url}\n\nНатисніть кнопку нижче.',public_replies=['Надіслали в Direct'],enabled=True)
        detail={'steps':[{'messages':[{'id':'message-1','isFirstMessage':True,'inlineButtons':[{'id':'button-1'}]}]}]}
        mcp.side_effect=['created',[{'id':'11111111-1111-4111-8111-111111111111','startMessages':['МІКРО']}],detail,{'ok':True},{'ok':True},{'ok':True},{'ok':True}]
        sync_to_chatplace(rule)
        setup=mcp.call_args_list[0].args;self.assertEqual(setup[0],'automations_quick_setup')
        self.assertEqual(setup[1]['triggerType'],['messageEquals','commentEquals']);self.assertEqual(setup[1]['autoAnswers'],['Надіслали в Direct']);self.assertIn('/get/microcement?',setup[1]['buttonLink'])
        self.assertNotIn('https://',setup[1]['welcomeMessage']);self.assertNotIn('{form_url}',setup[1]['welcomeMessage']);self.assertEqual(setup[1]['welcomeButton'],'Отримати техкарту')
        calls={call.args[0]:call.args[1] for call in mcp.call_args_list if len(call.args)>1}
        self.assertEqual(calls['automations_messages_update']['messageId'],'message-1');self.assertNotIn('https://',calls['automations_messages_update']['text'])
        self.assertEqual(calls['automations_inline_buttons_update']['buttonId'],'button-1');self.assertIn('/get/microcement?',calls['automations_inline_buttons_update']['url'])
        self.assertEqual(calls['automations_buttons_connect'],{'buttonId':'button-1'})
        rule.refresh_from_db();self.assertEqual(rule.chatplace_status,'active')
