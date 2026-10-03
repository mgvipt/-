from datetime import date
from decimal import Decimal
from django.test import TestCase
from .models import Account,Transaction,StatementRow,Category
from .statement_import import import_statement,parse_statement
from .statement_transfers import link_statement_transfer
H='Дата;Опис;Сума;Валюта;Курс;original_amount;original_currency;balance;balance_currency\n'
class LedgerIdentityTests(TestCase):
 def setUp(self):
  self.a=Account.objects.create(name='TEST *3095');self.b=Account.objects.create(name='TEST *2319')
 def row(self,desc='buy',amount='-10',balance='90',currency='UAH',original='10',original_currency='UAH',stamp='2026-10-03 12:00:00',rate='1'):
  return f'{stamp};{desc};{amount};{currency};{rate};{original};{original_currency};{balance};{currency}\n'
 def test_resave_reorder_overlap_and_same_second(self):
  r1=self.row();r2=self.row(desc='other',balance='80');r3=self.row(desc='buy',balance='70')
  self.assertEqual(import_statement(H+r1+r2,self.a,commit=True)['created'],2)
  repeat=import_statement(H+r2+r1,self.a,commit=True);self.assertEqual((repeat['created'],repeat['duplicates']),(0,2))
  overlap=import_statement(H+r2+r3,self.a,commit=True);self.assertEqual((overlap['created'],overlap['duplicates']),(1,1))
  self.assertEqual(Transaction.objects.count(),3)
 def test_decimal_format_normalized_and_metadata_preserved(self):
  import_statement(H+self.row(),self.a,commit=True)
  self.assertEqual(import_statement(H+self.row(amount='-10.00',balance='90.00',original='10.00'),self.a,commit=True)['duplicates'],1)
  self.assertEqual(StatementRow.objects.get().source_data['balance'],'90.00')
 def test_manual_classification_and_comment_preserved(self):
  import_statement(H+self.row(),self.a,commit=True);t=Transaction.objects.get();t.comment='MANUAL';t.category=Category.objects.create(name='MANUAL',direction='out');t.save()
  self.assertEqual(import_statement(H+self.row(),self.a,commit=True)['duplicates'],1);t.refresh_from_db();self.assertEqual(t.comment,'MANUAL');self.assertEqual(t.category.name,'MANUAL')
 def test_full_signature_changes_same_second_not_merged(self):
  import_statement(H+self.row(),self.a,commit=True)
  self.assertEqual(import_statement(H+self.row(original='9.75'),self.a,commit=True)['created'],1)
 def test_missing_fx_review_and_closed_period_even_admin_service(self):
  p=import_statement(H+self.row(amount='-1',currency='USD',original='1',original_currency='USD',rate=''),self.a,commit=True)
  self.assertEqual(p['review'],1);self.assertEqual(p['preview'][0]['amount'],'1')
  p=import_statement(H+self.row(stamp='2026-10-02 12:00:00'),self.a,commit=True,closed_until=date(2026,10,2));self.assertEqual(p['skipped_closed'],1);self.assertEqual(Transaction.objects.count(),0)
 def pair(self):
  s=H+self.row(desc='Переказ на картку *2319',amount='-400',balance='600',original='10',original_currency='USD')
  d=H+self.row(desc='Переказ з картки *3095',amount='10',balance='20',currency='USD',original='400',original_currency='UAH',rate='',stamp='2026-10-03 12:00:02')
  return s,d,parse_statement(s,self.a)[0][0]['key'],parse_statement(d,self.b)[0][0]['key']
 def test_two_legs_one_transfer_repeat_and_individual_repeat(self):
  s,d,sk,dk=self.pair();p=link_statement_transfer(self.a,s,sk,self.b,d,dk);self.assertEqual(p['new_transactions'],1);self.assertEqual(Transaction.objects.count(),0)
  p=link_statement_transfer(self.a,s,sk,self.b,d,dk,commit=True);self.assertEqual(StatementRow.objects.count(),2);self.assertEqual(Transaction.objects.count(),1)
  t=Transaction.objects.get();self.assertEqual((t.direction,t.amount,t.transfer_amount),('transfer',Decimal('400'),Decimal('10')))
  self.assertTrue(link_statement_transfer(self.a,s,sk,self.b,d,dk,commit=True)['duplicate'])
  self.assertEqual(import_statement(s,self.a,commit=True)['duplicates'],1)
  self.assertEqual(import_statement(d,self.b,commit=True)['duplicates'],1)
 def test_pair_existing_transfer_preserves_manual_fields(self):
  s,d,sk,dk=self.pair();t=Transaction.objects.create(account=self.a,transfer_account=self.b,direction='transfer',date=date(2026,10,3),op_time='12:00:00',amount=400,transfer_amount=10,currency='UAH',rate=1,comment='MANUAL')
  p=link_statement_transfer(self.a,s,sk,self.b,d,dk,commit=True,existing_transfer_id=t.pk);self.assertEqual(p['new_transactions'],0);t.refresh_from_db();self.assertEqual(t.comment,'MANUAL')
 def test_pair_legacy_legs_and_closed_period_block(self):
  s,d,sk,dk=self.pair();Transaction.objects.create(account=self.a,direction='out',date=date(2026,10,3),amount=400,currency='UAH',rate=1)
  with self.assertRaises(ValueError):link_statement_transfer(self.a,s,sk,self.b,d,dk,commit=True)
  with self.assertRaises(ValueError):link_statement_transfer(self.a,s,sk,self.b,d,dk,commit=True,closed_until=date(2026,10,3))
  self.assertEqual(Transaction.objects.count(),1)

 def test_source_card_provenance_survives_different_crm_label(self):
  self.a.name='TEST *3580';self.a.save();src,dst,_,_=self.pair()
  src=src.replace(H,H.rstrip('\n')+';card\n').replace('12:00:00;','12:00:00;').rstrip('\n')+';3095\n'
  dst=dst.replace(H,H.rstrip('\n')+';card\n').rstrip('\n')+';2319\n'
  sk=parse_statement(src,self.a)[0][0]['key'];dk=parse_statement(dst,self.b)[0][0]['key']
  result=link_statement_transfer(self.a,src,sk,self.b,dst,dk,commit=True)
  self.assertTrue(result['committed']);self.assertEqual(StatementRow.objects.get(key=sk).source_data['source_card'],'3095')


 def test_legacy_original_amount_does_not_duplicate_card_fee_total(self):
  Transaction.objects.create(account=self.a,direction='out',amount=10,currency='UAH',rate=1,date=date(2026,10,3),op_time='12:00:01',comment='MANUAL original amount')
  result=import_statement(H+self.row(amount='-10.50',balance='89.50',original='10'),self.a,commit=True)
  self.assertEqual(result['created'],0);self.assertEqual(result['review'],1);self.assertEqual(Transaction.objects.count(),1)


 def test_own_funds_without_word_card_require_transfer_review(self):
  result=import_statement(H+self.row(desc='Зарахування, ФОП. Коментар: Переказ власних коштiв',amount='10',balance='110'),self.a,commit=True)
  self.assertEqual(result['created'],0);self.assertEqual(result['review'],1);self.assertEqual(Transaction.objects.count(),0)


class RealFormatConversionTests(TestCase):
 def test_actual_ukrainian_headers_category_and_zero_balance(self):
  import io
  from openpyxl import Workbook
  from django.contrib.auth import get_user_model
  from django.core.files.uploadedfile import SimpleUploadedFile
  from rest_framework.test import APIClient
  a=Account.objects.create(name='TEST card');u=get_user_model().objects.create_user('test-xlsx',is_superuser=True)
  c=APIClient();c.force_authenticate(u);w=Workbook();s=w.active;s.title='Виписки';s.append(['TEST period'])
  s.append(['Дата','Категорія','Картка','Опис операції','Сума в валюті картки','Валюта картки','Сума в валюті транзакції','Валюта транзакції','Залишок на кінець періоду','Валюта залишку'])
  s.append(['03.10.2026 13:00:00','CAT1','','Interest',-91.36,'UAH',91.36,'UAH',0,'UAH'])
  def convert():
   b=io.BytesIO();w.save(b);r=c.post('/api/transactions/privat-xlsx-csv/',{'file':SimpleUploadedFile('TEST.xlsx',b.getvalue())},format='multipart',HTTP_HOST='crm.wallcovdec.com.ua');self.assertEqual(r.status_code,200);return r.data['csv']
  csv1=convert();r,_=parse_statement(csv1,a);self.assertTrue(r[0]['complete_identity']);self.assertEqual(r[0]['source_data']['balance'],'0.00');self.assertEqual(r[0]['description'],'Interest')
  import_statement(csv1,a,commit=True);s.cell(3,2).value='CAT2';self.assertEqual(import_statement(convert(),a,commit=True)['duplicates'],1);self.assertEqual(Transaction.objects.count(),1)

class ClosedDayImportApiTests(TestCase):
 def test_admin_cannot_import_behind_active_day_snapshot(self):
  from django.contrib.auth import get_user_model
  from rest_framework.test import APIClient
  from .models import DaySnapshot
  u=get_user_model().objects.create_user('test-closed-admin',is_superuser=True);a=Account.objects.create(name='TEST closed')
  DaySnapshot.objects.create(date=date(2026,10,2),version=1,kind='manual',rows=[],totals={})
  c=APIClient();c.force_authenticate(u)
  r=c.post('/api/transactions/import-statement/',{'account':a.pk,'commit':True,'data':H+'2026-10-01 12:00:00;buy;-10;UAH;1;10;UAH;90;UAH\n'},format='json',HTTP_HOST='crm.wallcovdec.com.ua')
  self.assertEqual(r.status_code,200);self.assertEqual(r.data['created'],0);self.assertEqual(r.data['skipped_closed'],1);self.assertEqual(Transaction.objects.count(),0);self.assertEqual(DaySnapshot.objects.count(),1)

class LegacyReconciliationTests(TestCase):
 def setUp(self):
  self.a=Account.objects.create(name='TEST legacy');self.csv=H+'2026-10-03 12:00:00;bank description;-10;UAH;1;10;UAH;90;UAH\n'
  self.key=parse_statement(self.csv,self.a)[0][0]['key'];self.tx=Transaction.objects.create(account=self.a,direction='out',date=date(2026,10,3),op_time='12:00:00',amount=10,currency='UAH',rate=1,comment='MANUAL')
 def test_explicit_legacy_link_repeat_without_financial_changes(self):
  from .statement_links import link_existing_statement
  with self.assertRaises(ValueError):link_existing_statement(self.a,self.csv,self.key,self.tx.pk,commit=True)
  link_existing_statement(self.a,self.csv,self.key,self.tx.pk,commit=True,confirm_existing=True,reason='Confirmed bank evidence')
  self.tx.refresh_from_db();self.assertEqual(self.tx.comment,'MANUAL');self.assertEqual(Transaction.objects.count(),1)
  self.assertEqual(import_statement(self.csv,self.a,commit=True)['duplicates'],1)
 def test_closed_legacy_link_and_time_disagreement_require_resolution(self):
  from .statement_links import link_existing_statement
  with self.assertRaises(ValueError):link_existing_statement(self.a,self.csv,self.key,self.tx.pk,commit=True,confirm_existing=True,reason='Confirmed bank evidence',closed_until=date(2026,10,3))
  self.tx.op_time='12:01:00';self.tx.save()
  with self.assertRaises(ValueError):link_existing_statement(self.a,self.csv,self.key,self.tx.pk,commit=True,confirm_existing=True,reason='Confirmed bank evidence')
  self.assertEqual(StatementRow.objects.count(),0)

class AccountScopedHistoryTests(TestCase):
 def setUp(self):
  from django.contrib.auth import get_user_model
  from rest_framework.test import APIClient
  from .models import DaySnapshot
  from .statement_history import ledger_digest,snapshots_digest,PROVIDER
  from apps.integrations.models import IntegrationSettings
  self.a=Account.objects.create(name='TEST card');self.offline=Account.objects.create(name='TEST closed cash',kind='cash')
  self.old=Transaction.objects.create(account=self.offline,direction='in',amount=50,date=date(2026,10,2),comment='OFFLINE')
  self.snap=DaySnapshot.objects.create(date=date(2026,10,2),version=1,rows=[{'account_id':self.offline.pk,'amount':50}],totals={'balances':[{'id':self.offline.pk,'system':50,'fact':50}]})
  self.csv=H+'2026-10-01 12:00:00;buy;-10;UAH;1;10;UAH;90;UAH\n';self.key=parse_statement(self.csv,self.a)[0][0]['key']
  self.u=get_user_model().objects.create_user('TEST history owner',is_superuser=True);self.c=APIClient();self.c.force_authenticate(self.u)
  self.approval=IntegrationSettings.objects.create(provider=PROVIDER,is_active=True,config={'approval_id':'TEST_APPROVED_ONLY','approved':True,'backup_verified':True,'restore_tested':True,'backup_sha256':'0'*64,'account_ids':[self.a.pk],'date_from':'2026-05-01','date_to':'2026-10-02','new_keys':[self.key],'legacy_links':{},'transfer_pairs':{},'rates':{},'ledger_digest':ledger_digest([self.a.pk]),'snapshots_digest':snapshots_digest(date(2026,10,2))})
 def post(self,**kwargs):
  return self.c.post('/api/transactions/import-statement/',{'account':self.a.pk,'data':self.csv,'commit':True,'historical_approval':'TEST_APPROVED_ONLY',**kwargs},format='json',HTTP_HOST='crm.wallcovdec.com.ua')
 def test_scoped_add_repeat_keeps_offline_and_snapshots(self):
  oldrows=self.snap.rows;oldtotals=self.snap.totals
  r=self.post();self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.data['created'],1)
  r=self.post();self.assertEqual(r.data['created'],0);self.assertEqual(r.data['duplicates'],1)
  self.old.refresh_from_db();self.snap.refresh_from_db();self.assertEqual(self.old.amount,50);self.assertEqual(self.old.comment,'OFFLINE');self.assertEqual(self.snap.rows,oldrows);self.assertEqual(self.snap.totals,oldtotals);self.assertIsNone(self.snap.reopened_at)
  self.approval.refresh_from_db();self.assertEqual(len(self.approval.config['audit']),2)
 def test_different_account_and_unconfirmed_key_block(self):
  r=self.post(account=self.offline.pk);self.assertEqual(r.status_code,400);self.assertEqual(Transaction.objects.filter(account=self.a).count(),0)
  self.approval.config['new_keys']=[];self.approval.save();r=self.post();self.assertEqual(r.data['created'],0);self.assertEqual(r.data['review'],1)
 def test_backup_and_stale_state_block(self):
  self.approval.config['backup_verified']=False;self.approval.save();self.assertEqual(self.post().status_code,400)
  self.approval.config['backup_verified']=True;self.approval.config['ledger_digest']='stale';self.approval.save();self.assertEqual(self.post().status_code,400);self.assertEqual(Transaction.objects.filter(account=self.a).count(),0)
 def test_accounting_lock_is_not_bypassed(self):
  from apps.integrations.models import IntegrationSettings
  IntegrationSettings.objects.create(provider='finance_lock',config={'closed_until':'2026-10-02'})
  r=self.post();self.assertEqual(r.data['created'],0);self.assertEqual(r.data['skipped_closed'],1)
 def test_historical_fx_only_approved_per_row_rate(self):
  self.csv=H+'2026-10-01 12:00:00;USD buy;-10;USD;;10;USD;90;USD\n';key=parse_statement(self.csv,self.a)[0][0]['key']
  self.approval.config['new_keys']=[key];self.approval.save()
  r=self.post(rate='999');self.assertEqual(r.data['created'],0);self.assertEqual(r.data['review'],1)
  self.approval.refresh_from_db();self.approval.config['rates']={key:'40'};self.approval.save();r=self.post(rate='999');self.assertEqual(r.data['created'],1)
  t=Transaction.objects.get(account=self.a);self.assertEqual(t.amount,10);self.assertEqual(t.amount_uah,400)
 def test_historical_transfer_pair_keeps_closed_offline(self):
  from .statement_history import ledger_digest
  from .statement_import import digest
  b=Account.objects.create(name='TEST destination')
  h=H.rstrip('\n')+';card\n'
  src=h+'2026-10-01 12:00:00;На свою картку *2319;-400;UAH;1;400;UAH;600;UAH;3095\n'
  dst=h+'2026-10-01 12:00:02;Зі своєї картки *3095;10;USD;;10;USD;20;USD;2319\n'
  sk=parse_statement(src,self.a)[0][0]['key'];dk=parse_statement(dst,b)[0][0]['key']
  self.approval.config['account_ids']=[self.a.pk,b.pk];self.approval.config['ledger_digest']=ledger_digest([self.a.pk,b.pk]);self.approval.config['transfer_pairs']={digest([sk,dk]):None};self.approval.save()
  data={'source_account':self.a.pk,'destination_account':b.pk,'source_csv':src,'destination_csv':dst,'source_key':sk,'destination_key':dk,'historical_approval':'TEST_APPROVED_ONLY','commit':True}
  r=self.c.post('/api/transactions/link-statement-transfer/',data,format='json',HTTP_HOST='crm.wallcovdec.com.ua');self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.data['new_transactions'],1)
  r=self.c.post('/api/transactions/link-statement-transfer/',data,format='json',HTTP_HOST='crm.wallcovdec.com.ua');self.assertEqual(r.status_code,200,r.data);self.assertTrue(r.data['duplicate'])
  self.old.refresh_from_db();self.snap.refresh_from_db();self.assertEqual(self.old.amount,50);self.assertIsNone(self.snap.reopened_at);self.assertEqual(StatementRow.objects.count(),2)
