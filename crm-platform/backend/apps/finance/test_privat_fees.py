from copy import deepcopy
from decimal import Decimal
from django.test import TestCase
from .models import Account, Category, Transaction
from .privat_fees import import_privat_fee, fee_details

class PrivatFeeTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(name="Bank 7404")
        self.other = Account.objects.create(name="Bank 1493")
        self.cat = Category.objects.create(name="Комиссии банка и проценты", direction="out")
        self.row = dict(REF="SHARED", REFN="Z", ID="SHAREDZ-time-D",
            TRANTYPE="D", CCY="UAH", SUM="50.00", DAT_OD="06.07.2026",
            TIM_P="08:58", OSND="Комісія за поповнення карток")
    def test_same_ref_principal_other_account_and_replay(self):
        principal=Transaction.objects.create(account=self.other, direction="transfer", amount=10000,
            date="2026-07-06", comment="PB#SHARED/D · Переказ власних коштів")
        tx,created=import_privat_fee(self.row,self.account,"PB-test")
        self.assertTrue(created)
        self.assertEqual(tx.amount,Decimal("50"))
        self.assertEqual(import_privat_fee(self.row,self.account,"PB-repeat"),(tx,False))
        principal.refresh_from_db()
        self.assertEqual(principal.comment,"PB#SHARED/D · Переказ власних коштів")
    def test_fee_first_does_not_block_principal(self):
        import_privat_fee(self.row,self.account,"PB-test")
        self.assertFalse(Transaction.objects.filter(comment__startswith="PB#SHARED/D").exists())
    def test_same_ref_principal_same_account_same_amount_is_not_fee(self):
        Transaction.objects.create(account=self.account,direction="out",amount=50,
            date="2026-07-06",comment="PB#SHARED/D · Оплата товару")
        self.assertTrue(import_privat_fee(self.row,self.account,"PB-test")[1])
    def test_distinct_accounts_and_legs(self):
        import_privat_fee(self.row,self.account,"PB-test")
        self.assertTrue(import_privat_fee(self.row,self.other,"PB-test")[1])
        second=dict(self.row,REFN="Y")
        self.assertTrue(import_privat_fee(second,self.account,"PB-test")[1])
    def test_final_posting_time_and_manual_edits_preserved(self):
        tx,_=import_privat_fee(self.row,self.account,"PB-test")
        tx.category=None;tx.counterparty="Manual";tx.amount=Decimal("49");tx.save()
        row=dict(self.row,ID="changed-final-time",TIM_P="09:02")
        again,created=import_privat_fee(row,self.account,"PB-repeat")
        self.assertFalse(created)
        self.assertEqual(again.amount,Decimal("49"))
        self.assertEqual(again.counterparty,"Manual")
        self.assertIsNone(again.category)
    def test_finmap_fee_not_duplicated_and_dry_run_no_writes(self):
        old=Transaction.objects.create(account=self.account,direction="out",amount=50,
            date="2026-07-06",op_time="08:58:04",import_batch="FM-FULL",
            comment=self.row["OSND"]+" НЕЦІЛЬОВЕ")
        self.assertEqual(import_privat_fee(self.row,self.account,"PB-test"),(old,False))
        row=dict(self.row,REF="NEW",SUM="75")
        self.assertEqual(import_privat_fee(row,self.account,"PB-test",dry_run=True),(None,True))
        self.assertEqual(Transaction.objects.count(),1)
    def test_legacy_pb_fee_no_duplicate(self):
        old=Transaction.objects.create(account=self.account,direction="out",amount=50,
            date="2026-07-06",comment="PB#SHARED/D · "+self.row["OSND"])
        self.assertEqual(import_privat_fee(self.row,self.account,"PB-test"),(old,False))
    def test_non_fee_and_merged_manual_transfer_unaffected(self):
        row=dict(self.row,TRANTYPE="C",OSND="за товар",REF="RUDYUK")
        old=Transaction.objects.create(account=self.other,transfer_account=self.account,
            direction="transfer",amount=200000,date="2026-09-08",
            comment="PB#RUDYUK/C · Confirmed cash to bank")
        self.assertIsNone(import_privat_fee(row,self.account,"PB-test"))
        self.assertTrue(Transaction.objects.filter(comment__startswith="PB#RUDYUK/C",pk=old.pk).exists())

    def test_real_pull_shared_ref_replay_and_merged_transfer(self):
        import io, json
        from unittest.mock import patch
        from .views import privat_pull
        Transaction.objects.create(account=self.other,direction="transfer",amount=10000,
            date="2026-07-06",comment="PB#SHARED/D · Переказ власних коштів")
        merged=Transaction.objects.create(account=self.other,transfer_account=self.account,
            direction="transfer",amount=200000,date="2026-09-08",
            comment="PB#RUDYUK/C · Confirmed cash to bank")
        fee=dict(self.row,AUT_MY_ACC="test7404")
        principal=dict(fee,REFN="1",SUM="10000",AUT_MY_ACC="test1493",OSND="Переказ власних коштів")
        cash=dict(fee,REF="RUDYUK",TRANTYPE="C",SUM="200000",OSND="за товар")
        payload=json.dumps({"transactions":[fee,principal,cash],"exist_next_page":False}).encode()
        config={"token":"test", "acc_map":{"7404":self.account.pk,"1493":self.other.pk}}
        with patch("apps.finance.views._privat_cfg",return_value=config), patch(
                "urllib.request.urlopen",side_effect=lambda *a,**kw:io.BytesIO(payload)):
            first=privat_pull(d_from="2026-07-01",d_to="2026-09-10")
            second=privat_pull(d_from="2026-07-01",d_to="2026-09-10")
        self.assertEqual(first[:3],(1,5,None))
        self.assertEqual(second[:3],(0,6,None))
        self.assertEqual(Transaction.objects.count(),3)
        merged.refresh_from_db()
        self.assertEqual(merged.amount,Decimal("200000"))
