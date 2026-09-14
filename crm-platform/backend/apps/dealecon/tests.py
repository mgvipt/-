"""Економіка угоди (14.09.2026). Лише ізольована тестова БД (Postgres);
НП API і повідомлення клієнтам підмінено — жодних зовнішніх запитів."""
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Deal, DealItem, Funnel, Payment, Stage
from apps.finance.models import Account, Category, Transaction
from apps.warehouse.models import Product, WarehousePayrollEntry

from . import services
from .models import DealEconomics, DealEconSettings
from .services import compute, recompute, store_np_cost


class _Base(TestCase):
    def setUp(self):
        services._TABLES.clear()
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Нова", order=0)
        self.acc = Account.objects.create(name="LiqPay еквайринг", kind="acquiring")
        self.cat_fee = Category.objects.create(name="Комиссии банка и проценты", direction="out")
        self.cat_np_fee = Category.objects.create(name="Комиссия НоваПей", direction="out", parent=self.cat_fee)
        masters = Category.objects.create(name="ЗП мастерам (объекты/сверление)", direction="out")
        self.cat_drill = Category.objects.create(name="Алмазное сверление", direction="out", parent=masters)
        self.cat_tr = Category.objects.create(name="Доставка / логистика", direction="out")
        self.cat_ret = Category.objects.create(name="Возврат денег(не является прибылью)", direction="in")
        self.cat_other = Category.objects.create(name="Реклама", direction="out")
        self.goods = Product.objects.create(name="Шовк", cost=Decimal("100"), price=Decimal("300"))
        self.svc = Product.objects.create(name="Алмазне свердління", track_stock=False, cost_pct=Decimal("40"),
                                          price=Decimal("1000"))
        self.owner = User.objects.create_superuser(username="owner", password="x", email="o@example.com")
        self.emp = User.objects.create_user(username="pack", password="x")

    def deal(self, amount=1000, ttn="", np_data=None, parent=None):
        return Deal.objects.create(title="T", funnel=self.f, stage=self.st, amount=Decimal(str(amount)), ttn=ttn,
                                   np_data=np_data or {}, parent_deal=parent)

    def item(self, deal, product=None, qty=1, price=0, cost=0, name=""):
        return DealItem.objects.create(deal=deal, product=product, custom_name=name, quantity=Decimal(str(qty)),
                                       price=Decimal(str(price)), cost=Decimal(str(cost)))

    def tx(self, deal, amount, cat=None, comment="", cp="", direction="out"):
        return Transaction.objects.create(direction=direction, amount=Decimal(str(amount)), account=self.acc,
                                          category=cat, deal=deal, comment=comment, counterparty=cp)

    def payroll(self, deal, op, amount):
        return WarehousePayrollEntry.objects.create(employee=self.emp, work_date=timezone.localdate(), deal=deal,
                                                    op_type=op, amount=Decimal(str(amount)))


class ComputeTests(_Base):
    def test_cogs_snapshot_fallback_and_service_plan(self):
        d = self.deal(2600)
        self.item(d, self.goods, qty=2, price=300, cost=80)    # знімок: 160
        self.item(d, self.goods, qty=1, price=300, cost=0)     # знімка немає → поточна собівартість 100 (оцінка)
        self.item(d, self.svc, qty=1, price=1700, cost=680)    # послуга: план майстра 680 → «Роботи майстра»
        r = compute(d)
        self.assertEqual(r["revenue"], Decimal("2600.00"))
        self.assertEqual(r["cogs"], Decimal("260.00"))
        self.assertEqual(r["sources"]["cogs"]["kind"], "estimate")
        self.assertEqual(r["master_works"], Decimal("680.00"))
        self.assertEqual(r["sources"]["master_works"]["kind"], "estimate")
        self.assertEqual(r["margin"], Decimal("1660.00"))
        self.assertTrue(r["is_estimate"])

    def test_no_items_uses_card_estimate(self):
        r = compute(self.deal(1000))
        self.assertEqual((r["revenue"], r["cogs"], r["margin"]), (Decimal("1000.00"), Decimal("650.00"), Decimal("350.00")))

    def test_delivery_sender_shared_ttn_and_recipient(self):
        p = self.deal(3000, ttn="2045", np_data={"parcel": {"payer": "Sender"},
                                                 "np_cost": {"payer": "Sender", "cost": 400}})
        c = self.deal(1000, ttn="2045", parent=p)               # дозамовлення тією самою посилкою
        self.assertEqual(compute(p)["delivery"], Decimal("300.00"))
        self.assertEqual(compute(c)["delivery"], Decimal("100.00"))
        r = self.deal(1000, ttn="2046", np_data={"parcel": {"payer": "Recipient"}})
        self.assertEqual(compute(r)["delivery"], Decimal("0.00"))
        # у CRM «Sender», але НП каже «Recipient» — НП головніша
        x = self.deal(1000, ttn="2047", np_data={"parcel": {"payer": "Sender"}, "np_cost": {"payer": "Recipient", "cost": 90}})
        self.assertEqual(compute(x)["delivery"], Decimal("0.00"))

    def test_delivery_act_fallback_and_no_cost(self):
        a = self.deal(8000, ttn="3001", np_data={"parcel": {"payer": "Sender"}, "delivery_cost_total": 250.5})
        r = compute(a)
        self.assertEqual(r["delivery"], Decimal("250.50"))
        self.assertEqual(r["sources"]["delivery"]["parts"]["cost_src"], "np_act")
        b = self.deal(8000, ttn="3002", np_data={"parcel": {"payer": "Sender"}})
        r = compute(b)
        self.assertEqual(r["delivery"], Decimal("0.00"))
        self.assertIn("np_no_cost", [f["code"] for f in r["flags"]])

    def test_commission_liqpay_rates_fact_and_anomaly(self):
        d = self.deal(1000)
        pay = Payment.objects.create(deal=d, provider="liqpay", amount=Decimal("1000"), is_paid=True)
        r = compute(d)
        self.assertEqual((r["commission"], r["sources"]["commission"]["kind"]), (Decimal("13.00"), "estimate"))
        Payment.objects.filter(pk=pay.pk).update(created_at=timezone.make_aware(datetime(2026, 7, 1, 12, 0)))
        self.assertEqual(compute(d)["commission"], Decimal("15.00"))          # до 14.07 — 1,50%
        self.tx(d, "14.20", self.cat_fee, comment="PBFEE#REF1 · Комісія еквайрингу", cp="LiqPay")
        r = compute(d)
        self.assertEqual((r["commission"], r["sources"]["commission"]["kind"]), (Decimal("14.20"), "fact"))
        self.tx(d, "90", self.cat_fee, comment="PBFEE#REF2 · Комісія еквайрингу", cp="LiqPay")   # разом 10,4% — аномалія
        r = compute(d)
        self.assertEqual(r["commission"], Decimal("15.00"))
        self.assertIn("fee_liqpay_range", [f["code"] for f in r["flags"]])
        tiny = self.deal(1)                                       # 0,01 ₴ з 1 ₴ — округлення, не аномалія
        Payment.objects.create(deal=tiny, provider="liqpay", amount=Decimal("1"), is_paid=True)
        self.tx(tiny, "0.01", self.cat_fee, comment="PBFEE#REF3 · Комісія еквайрингу", cp="LiqPay")
        r = compute(tiny)
        self.assertEqual((r["commission"], r["flags"]), (Decimal("0.01"), []))

    def test_commission_novapay_and_cash(self):
        d = self.deal(2000)
        Payment.objects.create(deal=d, provider="np_cod", amount=Decimal("2000"), is_paid=False)
        self.assertEqual(compute(d)["commission"], Decimal("26.00"))
        self.tx(d, "37.40", self.cat_np_fee, cp="НоваПей", comment="PB#X · комісія НоваПей по сделці")
        r = compute(d)
        self.assertEqual((r["commission"], r["sources"]["commission"]["kind"]), (Decimal("37.40"), "fact"))
        c = self.deal(500)
        Payment.objects.create(deal=c, provider="cash", amount=Decimal("500"), is_paid=True)
        r = compute(c)
        self.assertEqual((r["commission"], r["sources"]["commission"]["kind"]), (Decimal("0.00"), "fact"))

    def test_packaging_labor_plus_material_once_per_ttn(self):
        p = self.deal(3000, ttn="4001")
        c = self.deal(500, ttn="4001", parent=p)
        self.payroll(p, "packing", 13)
        self.payroll(p, "shipment_weight", 15)
        self.payroll(p, "workday", 500)                          # оклад дня — не пакування
        r = compute(p)
        self.assertEqual((r["packaging"], r["sources"]["packaging"]["kind"]), (Decimal("50.00"), "mixed"))
        self.assertEqual(compute(c)["packaging"], Decimal("0.00"))  # матеріали — один раз на посилку
        DealEconSettings.objects.create(pk=1, pack_material_per_shipment=Decimal("30"))
        self.assertEqual(compute(p)["packaging"], Decimal("58.00"))

    def test_master_fact_replaces_plan_with_transport(self):
        d = self.deal(1700)
        self.item(d, self.svc, 1, 1700, 680)
        self.assertEqual(compute(d)["master_works"], Decimal("680.00"))
        self.tx(d, 500, self.cat_drill, cp="Майстер")
        self.tx(d, 600, self.cat_tr, cp="Савченко Віталій")
        self.tx(d, 85, self.cat_tr, cp="Нова Пошта")             # НП — не транспорт майстра
        self.tx(d, 999, self.cat_other)                          # чужа категорія
        r = compute(d)
        self.assertEqual((r["master_works"], r["sources"]["master_works"]["kind"]), (Decimal("1100.00"), "fact"))
        self.assertEqual(r["cogs"], Decimal("0.00"))
        self.assertEqual(r["margin"], Decimal("600.00"))          # план 680 НЕ додається до факту

    def test_returns_and_full_margin(self):
        d = self.deal(10000, ttn="5001", np_data={"np_cost": {"payer": "Sender", "cost": 537}})
        self.item(d, self.goods, 10, 1000, 300)
        Payment.objects.create(deal=d, provider="liqpay", amount=Decimal("10000"), is_paid=True)
        self.payroll(d, "packing", 20)
        self.tx(d, 200, self.cat_ret, cp="Клієнт", comment="Повернення LiqPay по сделці")
        r = compute(d)
        # 10000 − 3000 − 537 − 130 (LiqPay 1,3% оцінка) − (20 + 22) − 0 − 200
        self.assertEqual(r["margin"], Decimal("6091.00"))
        self.assertEqual(r["margin_pct"], Decimal("60.91"))
        self.assertEqual(r["returns"], Decimal("200.00"))


class RecomputeTests(_Base):
    def test_recompute_saves_and_lock_freezes(self):
        d = self.deal(1000)
        self.item(d, self.goods, 1, 1000, 400)
        recompute(d)
        self.assertEqual(DealEconomics.objects.get(deal=d).margin, Decimal("600.00"))
        DealEconomics.objects.filter(deal=d).update(locked=True)
        DealItem.objects.filter(deal=d).update(cost=Decimal("900"))
        r = recompute(d)
        self.assertTrue(r["locked"])
        self.assertEqual(r["margin"], Decimal("600.00"))
        self.assertEqual(DealEconomics.objects.get(deal=d).margin, Decimal("600.00"))

    def test_signals_new_deal_row_old_deal_only_if_row_exists(self):
        today = timezone.localdate()
        DealEconSettings.objects.create(pk=1, auto_from=today - timedelta(days=10))
        with self.captureOnCommitCallbacks(execute=True):
            d = self.deal(1000)
            self.item(d, self.goods, 1, 1000, 400)
            Payment.objects.create(deal=d, provider="liqpay", amount=Decimal("1000"), is_paid=True)
        row = DealEconomics.objects.get(deal=d)
        self.assertEqual((row.commission, row.margin), (Decimal("13.00"), Decimal("587.00")))
        # стара угода (bulk_create — без сигналу створення, як угода «до запуску»)
        old = Deal.objects.bulk_create([Deal(title="Old", funnel=self.f, stage=self.st, amount=Decimal("500"))])[0]
        Deal.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
        old.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(deal=old, provider="cash", amount=Decimal("500"), is_paid=True)
        self.assertFalse(DealEconomics.objects.filter(deal=old).exists())   # старі продажі — лише командою
        recompute(old)
        with self.captureOnCommitCallbacks(execute=True):
            self.tx(old, 120, self.cat_drill)                               # виплату майстру привʼязали пізніше
        self.assertEqual(DealEconomics.objects.get(deal=old).master_works, Decimal("120.00"))

    def test_signal_tx_relink_recomputes_both_deals(self):
        DealEconSettings.objects.create(pk=1, auto_from=timezone.localdate() - timedelta(days=1))
        with self.captureOnCommitCallbacks(execute=True):
            a, b = self.deal(1000), self.deal(1000)
            t = self.tx(a, 300, self.cat_drill)
        self.assertEqual(DealEconomics.objects.get(deal=a).master_works, Decimal("300.00"))
        with self.captureOnCommitCallbacks(execute=True):
            t.deal = b
            t.save()
        self.assertEqual(DealEconomics.objects.get(deal=a).master_works, Decimal("0.00"))
        self.assertEqual(DealEconomics.objects.get(deal=b).master_works, Decimal("300.00"))


class NpTests(_Base):
    def test_store_np_cost_adds_key_only(self):
        d = self.deal(1000, ttn="777", np_data={"msg_shipped": True, "parcel": {"payer": "Sender"},
                                                "delivery_acts": [{"act": "A1"}]})
        row = {"Number": "777", "PayerType": "Sender", "DocumentCost": "321", "DocumentWeight": "5.5", "StatusCode": "5"}
        self.assertTrue(store_np_cost(d, row, schedule=False))
        fresh = Deal.objects.get(pk=d.pk).np_data
        self.assertTrue(fresh["msg_shipped"])
        self.assertEqual(fresh["delivery_acts"], [{"act": "A1"}])
        self.assertEqual(fresh["np_cost"]["cost"], 321.0)
        self.assertEqual(d.np_data["np_cost"]["payer"], "Sender")          # і в памʼяті обʼєкта
        self.assertFalse(store_np_cost(d, row, schedule=False))           # те саме вдруге — не пишемо
        self.assertEqual(compute(Deal.objects.get(pk=d.pk))["delivery"], Decimal("321.00"))

    def test_poller_hook_keeps_other_keys_and_sends_nothing(self):
        d = self.deal(1000, ttn="888", np_data={"msg_shipped": True, "parcel": {"payer": "Sender"}})
        resp = {"data": [{"Number": "888", "StatusCode": "1", "Status": "Створено", "PayerType": "Sender",
                          "DocumentCost": "140", "DocumentWeight": "2"}]}
        with patch("apps.integrations.adapters.np_track", return_value=resp), \
                patch("apps.crm.management.commands.np_status_sync.send_message") as sm:
            call_command("np_status_sync", stdout=StringIO(), stderr=StringIO())
        nd = Deal.objects.get(pk=d.pk).np_data
        self.assertTrue(nd["msg_shipped"])
        self.assertEqual(nd["parcel"], {"payer": "Sender"})
        self.assertEqual(nd["np_cost"]["cost"], 140.0)
        sm.assert_not_called()


class ApiTests(_Base):
    def setUp(self):
        super().setUp()
        self.d = self.deal(1000)
        self.item(self.d, self.goods, 1, 1000, 400)
        self.mgr = User.objects.create_user(username="mgr", password="x")
        self.mgr.extra_permissions = ["product.cost.view", "deal.view.all"]
        self.mgr.save()
        self.plain = User.objects.create_user(username="plain", password="x")
        self.plain.extra_permissions = ["deal.view.all"]
        self.plain.save()
        self.c = APIClient()
        self.url = "/api/deal-economics/%d/" % self.d.pk

    def get(self, user, url):
        self.c.force_authenticate(user)
        return self.c.get(url)

    def test_card_permissions_and_recompute(self):
        r = self.get(self.owner, self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["key"] for x in r.data["lines"]],
                         ["revenue", "cogs", "delivery", "commission", "packaging", "master_works", "returns"])
        self.assertEqual(r.data["margin"], 600.0)
        self.assertTrue(r.data["can_recompute"])
        self.assertFalse(DealEconomics.objects.exists())                   # GET нічого не пише
        r = self.get(self.mgr, self.url)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["can_recompute"])
        self.assertEqual(self.get(self.plain, self.url).status_code, 403)  # без права собівартості
        self.assertEqual(self.get(self.mgr, self.url + "?recompute=1").status_code, 403)
        r = self.get(self.owner, self.url + "?recompute=1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["saved"])
        self.assertTrue(DealEconomics.objects.filter(deal=self.d).exists())
        self.assertEqual(self.get(self.owner, "/api/deal-economics/999999/").status_code, 404)

    def test_foreign_deal_hidden_by_scope(self):
        m = User.objects.create_user(username="own", password="x")
        m.extra_permissions = ["product.cost.view"]
        m.save()
        self.assertEqual(self.get(m, self.url).status_code, 404)

    def test_settings(self):
        r = self.get(self.owner, "/api/deal-economics/settings/")
        self.assertEqual((r.status_code, r.data["pack_material_per_shipment"]), (200, 22.0))
        self.c.force_authenticate(self.mgr)
        self.assertEqual(self.c.patch("/api/deal-economics/settings/", {"pack_material_per_shipment": 30},
                                      format="json").status_code, 403)
        self.c.force_authenticate(self.owner)
        r = self.c.patch("/api/deal-economics/settings/", {"pack_material_per_shipment": "30", "liqpay_rate_pct": 1.3},
                         format="json")
        self.assertEqual((r.status_code, r.data["pack_material_per_shipment"]), (200, 30.0))
        self.assertEqual(self.c.patch("/api/deal-economics/settings/", {"liqpay_rate_pct": 50},
                                      format="json").status_code, 400)


class CommandTests(_Base):
    def test_dry_writes_nothing_then_limit_then_lock(self):
        for _ in range(3):
            d = self.deal(1000)
            self.item(d, self.goods, 1, 1000, 400)
            Payment.objects.create(deal=d, provider="cash", amount=Decimal("1000"), is_paid=True)
        out = StringIO()
        call_command("recompute_deal_economics", stdout=out)
        self.assertIn("DRY", out.getvalue())
        self.assertIn("**Разом**", out.getvalue())
        self.assertFalse(DealEconomics.objects.exists())
        call_command("recompute_deal_economics", "--live", "--limit", "2", stdout=StringIO())
        self.assertEqual(DealEconomics.objects.count(), 2)
        call_command("recompute_deal_economics", "--live", "--lock", stdout=StringIO())
        self.assertEqual(DealEconomics.objects.filter(locked=True).count(), 3)
