"""Повернення товару (16.09.2026). Лише ізольована тестова БД (Postgres); зовнішніх запитів немає.

Що перевіряємо: склад (прихід «як новий», брак без документів, набори, без реалізації), сума угоди, ідемпотентність,
права (гроші — лише deal.refund / власник), журнал «Повернення коштів», аванс клієнта (2 місця дзеркально),
«Оплачено» в картці, економіка угоди без подвійного віднімання, ЗП менеджера з мінусом повернення, «Помилка співробітника»,
звіт «Повернення»."""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import PERMISSION_CHOICES, User
from apps.crm.models import ActivityLog, Contact, Deal, DealItem, Funnel, Payment, Stage
from apps.finance.models import Account, Category, Transaction
from apps.warehouse.models import (Product, ProductCategory, ProductComponent, StockDocument, StockMovement, Warehouse,
                                   WarehouseJob, WarehousePayrollEntry)
from apps.warehouse.services import realize_deal

from . import services
from .models import DealReturn

HOST = "crm.wallcovdec.com.ua"


class _Base(TestCase):
    def setUp(self):
        services._TABLES.clear()
        from apps.dealecon import services as dealecon_services
        dealecon_services._TABLES.clear()
        cache.clear()
        self.owner = User.objects.create_superuser(username="ret-owner", password="x", email="ro@example.test")
        self.mgr = User.objects.create_user(username="ret-mgr", password="x", first_name="Ілона", last_name="Тест",
                                            extra_permissions=["deal.view.all"])
        self.acct = User.objects.create_user(username="ret-acc", password="x", first_name="Бухгалтер",
                                             extra_permissions=["deal.refund"])
        self.whu = User.objects.create_user(username="ret-wh", password="x", first_name="Склад",
                                            extra_permissions=["warehouse.view"])
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Успішна угода", order=5)
        self.wh = Warehouse.objects.create(name="Основний склад", is_default=True)
        self.acc = Account.objects.create(name="ФОП картка", kind="bank")
        self.cat_in = Category.objects.create(name="Онлайн (Instagram/TikTok/сайт)", direction="in")
        self.cat_ret = Category.objects.create(name="Возврат товара(УДАЛЯТЬ В P&L и эту же сумму дохода тоже)", direction="out")
        self.silk_cat = ProductCategory.objects.create(name="Мокрий шовк")
        self.silk = Product.objects.create(name="Мокрий шовк Bianco", unit="кг", cost=Decimal("400"), price=Decimal("1000"),
                                           category=self.silk_cat)
        self.contact = Contact.objects.create(first_name="Марія", last_name="Клієнтка")
        self._receive(self.silk, 10, 400)

    def _receive(self, product, qty, price):
        doc = StockDocument.objects.create(kind="in", number="ПР-%s" % product.id, warehouse=self.wh)
        StockMovement.objects.create(document=doc, product=product, quantity=Decimal(str(qty)), price=Decimal(str(price)))

    def deal(self, qty=2, price=1000, cost=400, paid=None, realize=True, product=None):
        product = product or self.silk
        d = Deal.objects.create(title="Тест повернення", funnel=self.f, stage=self.st, contact=self.contact, owner=self.mgr,
                                amount=Decimal(str(qty * price)))
        it = DealItem.objects.create(deal=d, product=product, quantity=Decimal(str(qty)), price=Decimal(str(price)),
                                     cost=Decimal(str(cost)))
        if paid:
            Payment.objects.create(deal=d, provider="cash", amount=Decimal(str(paid)), is_paid=True)
            Transaction.objects.create(direction="in", amount=Decimal(str(paid)), account=self.acc, category=self.cat_in,
                                       deal=d, date=timezone.localdate())
        if realize:
            realize_deal(d, self.owner)
        return d, it

    def api(self, u):
        c = APIClient()
        c.force_authenticate(u)
        return c

    def ret(self, user, deal, lines, reason="color", **kw):
        body = {"lines": lines, "reason": reason}
        body.update(kw)
        return self.api(user).post("/api/returns/deal/%d/" % deal.id, body, format="json", HTTP_HOST=HOST)

    def money(self, user, ret_id, **body):
        return self.api(user).post("/api/returns/%d/money/" % ret_id, body, format="json", HTTP_HOST=HOST)

    def advance(self):
        r = self.api(self.owner).get("/api/contacts/%d/finance/" % self.contact.id, HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        return float(r.data["advance"])


class RegisterTests(_Base):
    def test_as_new_goes_back_to_stock_and_deal_shrinks(self):
        d, it = self.deal(paid=2000)
        self.assertEqual(self.silk.stock(), Decimal("8"))
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": "stock"}])
        self.assertEqual(r.status_code, 201, r.data)
        d.refresh_from_db()
        it.refresh_from_db()
        self.assertEqual(d.amount, Decimal("1000"))
        self.assertEqual(it.quantity, Decimal("1"))
        self.assertEqual(self.silk.stock(), Decimal("9"))
        ret = DealReturn.objects.get()
        doc = ret.receipt_doc
        self.assertEqual((doc.kind, doc.number, doc.posted), ("in", "ПВ-%d" % ret.id, True))
        self.assertEqual(list(doc.items.values_list("quantity", "price")), [(Decimal("1.00"), Decimal("400.00"))])
        self.assertEqual((ret.money_status, ret.money_due, ret.amount), ("pending", Decimal("1000.00"), Decimal("1000.00")))
        self.assertTrue(ActivityLog.objects.filter(kind="deal", object_id=d.id, action="Повернення товару").exists())
        # гроші менеджер не вирішує — лише бухгалтер / власник
        self.assertEqual(self.money(self.mgr, ret.id, mode="offset").status_code, 403)

    def test_full_return_deletes_line_keeps_snapshot(self):
        d, it = self.deal(paid=2000)
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 2, "destination": "stock"}])
        self.assertEqual(r.status_code, 201, r.data)
        d.refresh_from_db()
        self.assertFalse(DealItem.objects.filter(pk=it.id).exists())
        self.assertEqual(d.amount, Decimal("0"))
        ln = DealReturn.objects.get().lines.get()
        self.assertEqual((ln.sold_quantity, ln.quantity, ln.amount, ln.deal_item_id), (Decimal("2.00"), Decimal("2.00"), Decimal("2000.00"), it.id))
        self.assertEqual(self.silk.stock(), Decimal("10"))

    def test_min_price_line_full_return_goes_to_zero(self):
        drill = Product.objects.create(name="Свердління", unit="шт", price=Decimal("1000"), min_price=Decimal("1500"), track_stock=False)
        d, it = self.deal(qty=1, price=1000, cost=0, product=drill, realize=False)
        d.amount = Decimal("1500")
        d.save(update_fields=["amount"])
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": "writeoff"}])
        self.assertEqual(r.status_code, 201, r.data)
        d.refresh_from_db()
        self.assertEqual(d.amount, Decimal("0"))
        self.assertEqual(DealReturn.objects.get().amount, Decimal("1500.00"))

    def test_defect_creates_no_stock_doc_and_counts_loss(self):
        d, it = self.deal(paid=2000)
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": "defect"}], reason="damaged")
        self.assertEqual(r.status_code, 201, r.data)
        ret = DealReturn.objects.get()
        self.assertIsNone(ret.receipt_doc)
        self.assertEqual(self.silk.stock(), Decimal("8"))  # реалізація вже списала, на полицю не повертається
        self.assertEqual((ret.cost_loss, ret.cost_back), (Decimal("400.00"), Decimal("0.00")))
        from apps.dealecon.services import compute
        e = compute(d)
        self.assertEqual((e["revenue"], e["cogs"], e["returns"]), (Decimal("1000.00"), Decimal("400.00"), Decimal("400.00")))

    def test_qty_over_sold_rejected_nothing_changes(self):
        d, it = self.deal(paid=2000)
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 3, "destination": "stock"}])
        self.assertEqual(r.status_code, 400)
        d.refresh_from_db()
        self.assertEqual(d.amount, Decimal("2000"))
        self.assertEqual(DealReturn.objects.count(), 0)
        self.assertEqual(self.silk.stock(), Decimal("8"))

    def test_same_form_twice_creates_one_return(self):
        d, it = self.deal(paid=2000)
        line = [{"item": it.id, "quantity": 1, "destination": "stock"}]
        self.assertEqual(self.ret(self.mgr, d, line, client_key="k-1").status_code, 201)
        r2 = self.ret(self.mgr, d, line, client_key="k-1")
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.data["created"])
        it.refresh_from_db()
        self.assertEqual((DealReturn.objects.count(), it.quantity, self.silk.stock()), (1, Decimal("1"), Decimal("9")))

    def test_no_realization_no_stock_change(self):
        d, it = self.deal(paid=2000, realize=False)
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": "stock"}])
        self.assertEqual(r.status_code, 201, r.data)
        ret = DealReturn.objects.get()
        self.assertIsNone(ret.receipt_doc)
        self.assertIn("не оприбутковано", ret.stock_note)
        self.assertEqual(self.silk.stock(), Decimal("10"))

    def test_bundle_returns_components(self):
        comp = Product.objects.create(name="Компонент А", unit="кг", cost=Decimal("100"), price=Decimal("200"))
        self._receive(comp, 10, 100)
        bundle = Product.objects.create(name="Тестовий набір А", unit="шт", cost=Decimal("250"), price=Decimal("400"))
        ProductComponent.objects.create(bundle=bundle, component=comp, quantity=Decimal("2"))
        d, it = self.deal(qty=1, price=400, cost=250, paid=400, product=bundle)
        self.assertEqual(comp.stock(), Decimal("8"))
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": "stock"}])
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(comp.stock(), Decimal("10"))
        self.assertEqual(list(DealReturn.objects.get().receipt_doc.items.values_list("product_id", "quantity")),
                         [(comp.id, Decimal("2.00"))])

    def test_warehouse_user_only_with_shipment_task(self):
        d, it = self.deal(paid=2000)
        line = [{"item": it.id, "quantity": 1, "destination": "stock"}]
        self.assertEqual(self.ret(self.whu, d, line).status_code, 404)
        WarehouseJob.objects.create(deal=d, assignee=self.whu, status="shipped", shipped_at=timezone.now())
        self.assertEqual(self.ret(self.whu, d, line).status_code, 201)

    def test_warehouse_error_opens_existing_employee_error_flow(self):
        d, it = self.deal(paid=2000)
        job = WarehouseJob.objects.create(deal=d, assignee=self.whu, status="shipped", shipped_at=timezone.now())
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": "stock"}], reason="wh_error")
        self.assertEqual(r.status_code, 201, r.data)
        err = DealReturn.objects.get().error
        self.assertEqual((err.status, err.blamed_user_id, err.deduction_uah, err.deal_id, err.job_id, err.source),
                         ("suggested", self.whu.id, Decimal("500.00"), d.id, job.id, "manager"))
        self.assertEqual(WarehousePayrollEntry.objects.count(), 0)  # до підтвердження нічого не утримано
        c = self.api(self.owner).post("/api/warehouse/errors/%d/confirm/" % err.id, {}, format="json", HTTP_HOST=HOST)
        self.assertEqual(c.status_code, 200)
        self.assertEqual(WarehousePayrollEntry.objects.get(employee=self.whu).amount, Decimal("-500.00"))

    def test_manager_error_blames_deal_owner(self):
        d, it = self.deal(paid=2000)
        r = self.ret(self.acct, d, [{"item": it.id, "quantity": 1, "destination": "stock"}], reason="mgr_error")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(DealReturn.objects.get().error.blamed_user_id, self.mgr.id)

    def test_state_for_manager_and_accountant(self):
        d, it = self.deal(paid=2000)
        m = self.api(self.mgr).get("/api/returns/deal/%d/" % d.id, HTTP_HOST=HOST)
        self.assertEqual(m.status_code, 200)
        self.assertFalse(m.data["can_money"])
        self.assertNotIn("accounts", m.data)
        self.assertTrue(m.data["realized"])
        a = self.api(self.acct).get("/api/returns/deal/%d/" % d.id, HTTP_HOST=HOST)
        self.assertEqual(a.status_code, 200)
        self.assertTrue(a.data["can_money"])
        self.assertIn(self.acc.id, [x["id"] for x in a.data["accounts"]])


class MoneyTests(_Base):
    def _pending(self, paid=2000, dest="stock"):
        d, it = self.deal(paid=paid)
        r = self.ret(self.mgr, d, [{"item": it.id, "quantity": 1, "destination": dest}])
        self.assertEqual(r.status_code, 201, r.data)
        return d, DealReturn.objects.get()

    def test_permission_code_registered(self):
        self.assertIn("deal.refund", {c for c, _ in PERMISSION_CHOICES})
        self.assertTrue(self.acct.has_perm_code("deal.refund"))
        self.assertFalse(self.mgr.has_perm_code("deal.refund"))

    def test_refund_creates_journal_operation_once(self):
        d, ret = self._pending()
        self.assertEqual(self.advance(), 0.0)          # «чекає рішення» — не вільний аванс
        r = self.money(self.acct, ret.id, mode="refund", amount=1000, account=self.acc.id)
        self.assertEqual(r.status_code, 200, r.data)
        tx = Transaction.objects.get(direction="out", deal=d)
        self.assertEqual((tx.category_id, tx.amount, tx.account_id, tx.contact_id), (self.cat_ret.id, Decimal("1000.00"), self.acc.id, self.contact.id))
        ret.refresh_from_db()
        self.assertEqual((ret.money_status, ret.refund_tx_id), ("refund", tx.id))
        self.assertEqual(self.money(self.acct, ret.id, mode="refund", amount=1000, account=self.acc.id).status_code, 409)
        self.assertEqual(Transaction.objects.filter(direction="out", deal=d).count(), 1)
        card = self.api(self.owner).get("/api/deals/%d/" % d.id, HTTP_HOST=HOST)
        self.assertEqual(card.data["paid"], 1000.0)   # «Оплачено» в картці — мінус повернене
        self.assertEqual(self.advance(), 0.0)          # гроші повернуто — фантомного авансу немає

    def test_partial_refund_rest_stays_advance(self):
        d, ret = self._pending()
        r = self.money(self.acct, ret.id, mode="refund", amount=600, account=self.acc.id)
        self.assertEqual(r.status_code, 200, r.data)
        ret.refresh_from_db()
        self.assertIn("400", ret.money_comment)
        self.assertEqual(self.advance(), 400.0)

    def test_offset_keeps_money_as_client_advance(self):
        d, ret = self._pending()
        self.assertEqual(self.money(self.owner, ret.id, mode="offset").status_code, 200)
        self.assertFalse(Transaction.objects.filter(direction="out", deal=d).exists())
        self.assertEqual(self.advance(), 1000.0)

    def test_pending_blocks_pay_from_advance(self):
        d, ret = self._pending()
        d2, _it2 = self.deal(qty=1, paid=None, realize=False)
        r = self.api(self.owner).post("/api/deals/%d/accept_payment/" % d2.id, {"provider": "advance", "amount": 500},
                                      format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("аванс", str(r.data.get("detail", "")).lower())

    def test_nothing_due_when_client_underpaid(self):
        d, ret = self._pending(paid=1000)
        self.assertEqual((ret.money_status, ret.money_due), ("none", Decimal("0.00")))
        self.assertEqual(self.money(self.acct, ret.id, mode="offset").status_code, 409)

    def test_liqpay_mode_links_existing_refund_without_double_count(self):
        d, ret = self._pending()
        tx = Transaction.objects.create(direction="out", amount=Decimal("1000"), account=self.acc, category=self.cat_ret, deal=d,
                                        comment="Повернення LiqPay по сделці #%d (WCCRM-%d-abc)" % (d.id, d.id))
        st = self.api(self.acct).get("/api/returns/deal/%d/" % d.id, HTTP_HOST=HOST)
        self.assertEqual([x["id"] for x in st.data["liqpay_refunds"]], [tx.id])
        r = self.money(self.acct, ret.id, mode="liqpay", tx=tx.id)
        self.assertEqual(r.status_code, 200, r.data)
        ret.refresh_from_db()
        self.assertEqual((ret.money_status, ret.refund_tx_id), ("liqpay", tx.id))
        from apps.dealecon.services import compute
        self.assertEqual(compute(d)["returns"], Decimal("0.00"))

    def test_refund_not_double_counted_in_deal_economics(self):
        d, ret = self._pending()
        self.money(self.acct, ret.id, mode="refund", amount=1000, account=self.acc.id)
        from apps.dealecon.services import compute
        e = compute(d)
        self.assertEqual((e["revenue"], e["cogs"], e["returns"]), (Decimal("1000.00"), Decimal("400.00"), Decimal("0.00")))


class PayrollTests(_Base):
    def setUp(self):
        super().setUp()
        from apps.payroll.models import PayPolicy
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        self.today = timezone.localdate()
        self.period = self.today.strftime("%Y-%m")

    def _comp(self, kind, params):
        from apps.payroll.models import PayComponent, PayScheme
        s = PayScheme.objects.create(user=self.mgr, position="Менеджер", valid_from=self.today.replace(day=1), employment="none")
        return PayComponent.objects.create(scheme=s, kind=kind, params=params)

    def _return_and_refund(self, d, it):
        ret, _ = services.register_return(d, self.mgr, {"reason": "color", "lines": [{"item": it.id, "quantity": 1}]})
        services.settle_money(ret.id, self.acct, {"mode": "refund", "amount": "1000", "account": self.acc.id})
        cache.clear()

    def test_margin_share_minus_refund_and_detail_matches(self):
        from apps.payroll import detail_views, engine
        comp = self._comp("margin_share", {"funnels": [self.f.id], "pct_to_plan": 10})
        d, it = self.deal(paid=2000)
        self.assertEqual(engine.calc(self.mgr, self.period)["total"], 120)   # 2000 × маржа 60% × 10%
        self._return_and_refund(d, it)
        self.assertEqual(engine.calc(self.mgr, self.period)["total"], 60)    # (2000 − 1000) × 60% × 10%
        d1, d2 = engine.period_bounds(self.period)
        det = detail_views._d_margin(comp, self.mgr, self.period, d1, d2, engine.policy(), 1.0)
        self.assertEqual(det["total"], 60)
        self.assertTrue(any(str(r["source"]).startswith("↩") for r in det["rows"]))

    def test_revenue_share_minus_refund(self):
        from apps.payroll import engine
        self._comp("revenue_share", {"pct": 5, "basis": "own_payments"})
        d, it = self.deal(paid=2000)
        self.assertEqual(engine.calc(self.mgr, self.period)["total"], 100)
        self._return_and_refund(d, it)
        self.assertEqual(engine.calc(self.mgr, self.period)["total"], 50)

    def test_offset_does_not_reduce_pay(self):
        from apps.payroll import engine
        self._comp("revenue_share", {"pct": 5, "basis": "own_payments"})
        d, it = self.deal(paid=2000)
        ret, _ = services.register_return(d, self.mgr, {"reason": "color", "lines": [{"item": it.id, "quantity": 1}]})
        services.settle_money(ret.id, self.owner, {"mode": "offset"})
        cache.clear()
        self.assertEqual(engine.calc(self.mgr, self.period)["total"], 100)  # гроші лишились у компанії (аванс клієнта)


class ReportTests(_Base):
    def test_report_by_reason_material_person(self):
        d1, it1 = self.deal(paid=2000)
        d2, it2 = self.deal(paid=2000)
        self.assertEqual(self.ret(self.mgr, d1, [{"item": it1.id, "quantity": 1, "destination": "stock"}]).status_code, 201)
        self.assertEqual(self.ret(self.mgr, d2, [{"item": it2.id, "quantity": 1, "destination": "defect"}], reason="wh_error").status_code, 201)
        r = self.api(self.owner).get("/api/returns/report/", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200, r.data)
        t = r.data["totals"]
        self.assertEqual((t["count"], t["amount"], t["pending"], t["loss"]), (2, 2000.0, 2000.0, 400.0))
        self.assertEqual({x["label"]: x["count"] for x in r.data["by_reason"]}, {"Не підійшов колір": 1, "Помилка складу": 1})
        self.assertEqual(r.data["by_material"], [{"name": "Мокрий шовк", "count": 2, "amount": 2000.0}])
        self.assertEqual(r.data["by_person"], [{"name": "Ілона Тест", "count": 2, "amount": 2000.0, "errors": 1}])
        self.assertEqual(len(r.data["rows"]), 2)

    def test_report_needs_analytics_permission(self):
        self.assertEqual(self.api(self.mgr).get("/api/returns/report/", HTTP_HOST=HOST).status_code, 403)
