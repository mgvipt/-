"""Партнерська програма (14.09.2026): рівні, пороги, статус лише росте, правило ATM і мінімум 15 п.п.,
пріоритет «товар > підпапка > папка», перегляд без запису, права. Лише ізольована тестова БД."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Contact, Deal, DealItem, Funnel, Stage
from apps.finance.models import Account, Category, Transaction
from apps.warehouse.models import Product, ProductCategory
from .models import PartnerDiscountRule, PartnerLevel, PartnerRuleLog, PartnerSettings, PartnerStatus, PartnerStatusHistory
from .services import (RuleBook, atm_suggest, floor_step, level_for, margin_pp, max_discount, turnover_map,
                       upsert_rule)

D = Decimal


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner_partners", password="x", is_superuser=True, is_staff=True)
        self.mgr = User.objects.create_user("mgr_partners", password="x")
        self.mgr.extra_permissions = ["contact.view.all", "deal.view.all", "deal.view"]
        self.mgr.save()
        self.lv = {lv.name: lv for lv in PartnerLevel.objects.all()}
        self.funnel = Funnel.objects.create(name="21 Основний продукт")
        self.stage = Stage.objects.create(funnel=self.funnel, name="Нова", order=0)
        self.tech = Funnel.objects.create(name="Техническая(Тесты)")
        self.tech_stage = Stage.objects.create(funnel=self.tech, name="Нова", order=0)
        self.acc = Account.objects.create(name="Каса тест")
        self.cat_sale = Category.objects.create(name="Онлайн (Instagram/TikTok/сайт)", direction="in")
        self.cat_refund = Category.objects.create(name="Возврат денег(не является прибылью)", direction="out")
        self.root = ProductCategory.objects.create(name="1.3.1. WALLCOV Фактурні покриття")
        self.sub = ProductCategory.objects.create(name="Pattera", parent=self.root)
        self.test_sets = ProductCategory.objects.create(name="Тестові набори та викраски", parent=self.root)
        self.tools = ProductCategory.objects.create(name="1.6. ІНСТРУМЕНТИ")
        self.p66 = Product.objects.create(name="Покриття A", price=1000, cost=340, category=self.sub)   # маржа 66
        self.p22 = Product.objects.create(name="Шпатель", price=100, cost=78, category=self.tools)      # маржа 22
        self.p10 = Product.objects.create(name="Валик", price=100, cost=90, category=self.tools)        # маржа 10
        self.pnc = Product.objects.create(name="Без собівартості", price=500, cost=0, category=self.sub)
        self.ptest = Product.objects.create(name="Тестовий набір", price=400, cost=100, category=self.test_sets)
        self.st = PartnerSettings.get()
        self.client_owner = APIClient()
        self.client_owner.force_authenticate(self.owner)
        self.client_mgr = APIClient()
        self.client_mgr.force_authenticate(self.mgr)

    def contact(self, name="Партнер Тест"):
        return Contact.objects.create(first_name=name, kinds=["client"])

    def deal(self, contact, funnel=None):
        funnel = funnel or self.funnel
        stage = self.stage if funnel == self.funnel else self.tech_stage
        return Deal.objects.create(title="Угода", contact=contact, funnel=funnel, stage=stage)

    def pay(self, amount, deal=None, contact=None, direction="in", category=None, days_ago=0):
        with self.captureOnCommitCallbacks(execute=True):
            return Transaction.objects.create(direction=direction, amount=D(amount), account=self.acc, deal=deal,
                                              contact=contact, category=category or (self.cat_sale if direction == "in"
                                                                                     else self.cat_refund),
                                              date=timezone.localdate() - timedelta(days=days_ago))

    def rule(self, level, pct, category=None, product=None, excluded=False, reason=""):
        upsert_rule(self.lv[level], self.owner, "manual", category=category, product=product, pct=pct,
                    excluded=excluded, reason=reason)


class LevelsAndFormulaTests(_Base):
    def test_levels_seeded_with_olegs_thresholds(self):
        rows = [(lv.name, lv.threshold_uah, lv.margin_share) for lv in PartnerLevel.objects.order_by("order")]
        self.assertEqual(rows, [("Старт", D("0"), D("0.25")), ("Партнер", D("25000"), D("0.40")),
                                ("Золото", D("75000"), D("0.50")), ("Дилер", D("200000"), D("0.60"))])

    def test_settings_defaults_found_by_name(self):
        self.assertEqual(self.st.min_margin_pp, D("15"))
        self.assertEqual(self.st.round_step, D("5"))
        self.assertEqual(str(self.st.turnover_from), "2026-05-05")
        self.assertEqual(self.st.exclude_funnel_ids, [self.tech.id])
        self.assertEqual(self.st.no_discount_category_ids, [self.test_sets.id])
        self.assertEqual(self.st.start_fixed, {str(self.root.id): 15, str(self.tools.id): 10})
        self.assertFalse(self.st.auto_apply)

    def test_thresholds(self):
        levels = list(PartnerLevel.objects.order_by("order"))
        self.assertEqual(level_for(D("24999.99"), levels).name, "Старт")
        self.assertEqual(level_for(D("25000"), levels).name, "Партнер")
        self.assertEqual(level_for(D("74999"), levels).name, "Партнер")
        self.assertEqual(level_for(D("75000"), levels).name, "Золото")
        self.assertEqual(level_for(D("200000"), levels).name, "Дилер")

    def test_atm_suggestion_and_15pp_floor(self):
        self.assertEqual(margin_pp(self.p66), D("66"))
        self.assertEqual([atm_suggest(66, s, 15, 5) for s in ("0.25", "0.40", "0.50", "0.60")],
                         [D("15"), D("25"), D("30"), D("35")])
        self.assertEqual(atm_suggest(22, "0.25", 15, 5), D("5"))     # min(5.5, 7) → вниз до 5
        self.assertEqual(atm_suggest(18, "0.60", 15, 5), D("0"))     # min(10.8, 3) = 3 → 0
        self.assertIsNone(atm_suggest(None, "0.25", 15, 5))           # немає собівартості
        self.assertEqual(floor_step(D("14.99"), 5), D("10"))
        self.assertEqual(max_discount(D("22"), 15), D("7"))
        self.assertEqual(max_discount(D("10"), 15), D("0"))

    def test_service_margin_uses_cost_pct(self):
        drill = Product.objects.create(name="Свердління", price=1000, cost=0, cost_pct=40)
        self.assertEqual(margin_pp(drill), D("60"))
        self.assertIsNone(margin_pp(self.pnc))


class PrecedenceTests(_Base):
    def eff(self, product, level="Старт"):
        return RuleBook().effective(product, self.lv[level])

    def test_product_beats_subfolder_beats_folder(self):
        self.rule("Старт", 15, category=self.root)
        self.assertEqual((self.eff(self.p66)["pct"], self.eff(self.p66)["source"]), (D("15"), "category"))
        self.rule("Старт", 20, category=self.sub)
        self.assertEqual(self.eff(self.p66)["pct"], D("20"))
        self.assertEqual(self.eff(self.p66)["source_name"], "Pattera")
        self.rule("Старт", 5, product=self.p66)
        self.assertEqual((self.eff(self.p66)["pct"], self.eff(self.p66)["source"]), (D("5"), "product"))
        upsert_rule(self.lv["Старт"], self.owner, "manual", product=self.p66, remove=True)
        self.assertEqual(self.eff(self.p66)["pct"], D("20"))
        self.rule("Старт", 0, product=self.p66, excluded=True)
        self.assertEqual((self.eff(self.p66)["pct"], self.eff(self.p66)["source"]), (D("0"), "excluded"))

    def test_no_rule_no_cost_and_test_sets_give_zero(self):
        self.rule("Старт", 15, category=self.root)
        self.assertEqual(self.eff(self.p22)["source"], "none")            # інструменти без правила
        self.assertEqual(self.eff(self.p22)["pct"], D("0"))
        e = self.eff(self.pnc)
        self.assertEqual((e["pct"], e["note"]), (D("0"), "немає собівартості"))
        e = self.eff(self.ptest)
        self.assertEqual((e["pct"], e["source"]), (D("0"), "no_discount"))

    def test_category_rule_capped_to_keep_15pp(self):
        self.rule("Старт", 10, category=self.tools)
        e = self.eff(self.p22)
        self.assertEqual((e["pct"], e["capped"], e["left_pp"]), (D("7"), True, D("15")))
        e = self.eff(self.p10)
        self.assertEqual((e["pct"], e["capped"]), (D("0"), True))

    def test_rule_changes_are_logged(self):
        self.rule("Старт", 15, category=self.root)
        self.rule("Старт", 12, category=self.root)
        log = list(PartnerRuleLog.objects.order_by("id").values_list("old_pct", "new_pct"))
        self.assertEqual(log, [(None, D("15")), (D("15"), D("12"))])


class DiscountApiTests(_Base):
    def test_preview_writes_nothing_then_apply(self):
        body = {"target": "category", "category_id": self.tools.id, "values": {str(self.lv["Старт"].id): 10}}
        r = self.client_owner.post("/api/partners/discounts/preview/", body, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["dry_run"])
        after = r.data["levels"][0]["after"]
        self.assertEqual((after["n_products"], after["n_capped"], after["min_left_pp"]), (2, 2, 10.0))
        self.assertEqual(PartnerDiscountRule.objects.count(), 0)
        r = self.client_owner.post("/api/partners/discounts/apply/", body, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(PartnerDiscountRule.objects.get().pct, D("10"))
        self.assertEqual(PartnerRuleLog.objects.count(), 1)

    def test_product_exception_below_minimum_needs_right_and_reason(self):
        boss = User.objects.create_user("partners_manager", password="x")
        boss.extra_permissions = ["partners.manage", "partners.view", "product.cost.view"]
        boss.save()
        c = APIClient()
        c.force_authenticate(boss)
        body = {"target": "products", "product_ids": [self.p22.id], "values": {str(self.lv["Старт"].id): 12}}
        r = c.post("/api/partners/discounts/apply/", body, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("мінімальної маржі", r.data["detail"])
        r = self.client_owner.post("/api/partners/discounts/apply/", body, format="json")
        self.assertEqual(r.status_code, 400)                               # право є, причини немає
        body["reason"] = "розпродаж залишку"
        r = self.client_owner.post("/api/partners/discounts/apply/", body, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        e = RuleBook().effective(self.p22, self.lv["Старт"])
        self.assertEqual((e["pct"], e["override"]), (D("12"), True))

    def test_suggest_uses_olegs_start_and_atm_for_others(self):
        r = self.client_owner.post("/api/partners/discounts/suggest/", {"target": "categories"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        row = next(x for x in r.data["rows"] if x["category_id"] == self.root.id)
        got = {lv.name: row["levels"][lv.id]["suggested"] for lv in self.lv.values()}
        # «Старт» — затверджені Олегом 15%; інші — медіана ATM по товарах з собівартістю (тут одна маржа 66)
        self.assertEqual(got, {"Старт": 15.0, "Партнер": 25.0, "Золото": 30.0, "Дилер": 35.0})
        self.assertEqual(PartnerDiscountRule.objects.count(), 0)

    def test_matrix_and_permissions(self):
        self.assertEqual(self.client_mgr.get("/api/partners/levels/").status_code, 200)
        self.assertEqual(self.client_mgr.get("/api/partners/matrix/").status_code, 403)
        r = self.client_mgr.patch("/api/partners/levels/%s/" % self.lv["Партнер"].id, {"threshold_uah": 1}, format="json")
        self.assertEqual(r.status_code, 403)
        self.mgr.extra_permissions = self.mgr.extra_permissions + ["partners.view"]
        self.mgr.save()
        r = self.client_mgr.get("/api/partners/matrix/")
        self.assertEqual(r.status_code, 200)
        cell = r.data["categories"][0]["cells"][self.lv["Старт"].id]
        self.assertNotIn("avg_left_pp", cell)                               # без права собівартості маржі не видно
        r = self.client_owner.get("/api/partners/matrix/")
        self.assertIn("avg_left_pp", r.data["categories"][0]["cells"][self.lv["Старт"].id])

    def test_level_rules(self):
        r = self.client_owner.patch("/api/partners/levels/%s/" % self.lv["Партнер"].id, {"threshold_uah": 100000},
                                    format="json")
        self.assertEqual(r.status_code, 400)                                # вище за «Золото»
        r = self.client_owner.patch("/api/partners/levels/%s/" % self.lv["Партнер"].id, {"threshold_uah": 30000,
                                                                                         "name": "Партнер+"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client_owner.patch("/api/partners/settings/", {"auto_apply": True},
                                                 format="json").status_code, 400)
        self.assertEqual(self.client_owner.delete("/api/partners/levels/%s/" % self.lv["Дилер"].id).status_code, 405)


class StatusTests(_Base):
    def post(self, client, contact, **body):
        return client.post("/api/partners/contacts/%s/" % contact.id, body, format="json")

    def test_manager_cannot_assign(self):
        c = self.contact()
        self.assertEqual(self.post(self.client_mgr, c, action="mark").status_code, 403)
        self.assertEqual(self.client_mgr.get("/api/partners/contacts/%s/" % c.id).status_code, 200)
        self.assertFalse(PartnerStatus.objects.exists())

    def test_mark_gives_start_and_payment_raises_never_drops(self):
        c = self.contact()
        r = self.post(self.client_owner, c, action="mark")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["level"]["name"], "Старт")
        self.assertEqual(r.data["next_level"]["name"], "Партнер")
        self.assertEqual(r.data["to_next_uah"], 25000.0)
        deal = self.deal(c)
        self.pay(25000, deal=deal)                                           # сигнал після оплати
        s = PartnerStatus.objects.get(contact=c)
        self.assertEqual((s.level.name, s.turnover_uah), ("Партнер", D("25000")))
        self.assertTrue(PartnerStatusHistory.objects.filter(contact=c, reason="auto_raise").exists())
        self.pay(10000, deal=deal, direction="out", category=self.cat_refund)  # повернення: оборот 15 000
        s.refresh_from_db()
        self.assertEqual((s.level.name, s.turnover_uah), ("Партнер", D("15000")))   # рівень не впав
        r = self.post(self.client_owner, c, action="raise", level_id=self.lv["Старт"].id)
        self.assertEqual(r.status_code, 400)                                 # знизити не можна навіть власнику
        r = self.post(self.client_owner, c, action="raise", level_id=self.lv["Золото"].id, note="домовленість")
        self.assertEqual(r.data["level"]["name"], "Золото")
        r = self.post(self.client_owner, c, action="unmark")
        self.assertEqual((r.data["is_partner"], r.data["level"]["name"]), (False, "Золото"))
        r = self.post(self.client_owner, c, action="mark")
        self.assertEqual((r.data["is_partner"], r.data["level"]["name"]), (True, "Золото"))
        reasons = list(PartnerStatusHistory.objects.filter(contact=c).order_by("id").values_list("reason", flat=True))
        self.assertEqual(reasons, ["assign", "auto_raise", "manual", "unmark", "remark"])

    def test_mark_with_existing_turnover_rises_at_once(self):
        c = self.contact()
        self.pay(80000, deal=self.deal(c))                                   # до відмітки — сигнал нічого не робить
        self.assertFalse(PartnerStatus.objects.exists())
        r = self.post(self.client_owner, c, action="mark")
        self.assertEqual(r.data["level"]["name"], "Золото")

    def test_turnover_rules(self):
        c = self.contact()
        self.pay(1000, deal=self.deal(c))                                    # рахується
        self.pay(2000, contact=c)                                            # без угоди, але з клієнтом — рахується
        self.pay(4000, deal=self.deal(c, funnel=self.tech))                  # тестова воронка — ні
        self.pay(8000, deal=self.deal(c), days_ago=(timezone.localdate() - self.st.turnover_from).days + 1)  # до 05.05
        self.assertEqual(turnover_map([c.id])[c.id], D("3000"))

    def test_sweep_dry_run_then_apply(self):
        c = self.contact()
        PartnerStatus.objects.create(contact=c, level=self.lv["Старт"])
        Transaction.objects.create(direction="in", amount=D(30000), account=self.acc, deal=self.deal(c),
                                   category=self.cat_sale)                   # без on_commit — сигнал не спрацював
        out = StringIO()
        call_command("partners_sweep", stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertEqual(PartnerStatus.objects.get(contact=c).level.name, "Старт")
        call_command("partners_sweep", "--apply", stdout=StringIO())
        self.assertEqual(PartnerStatus.objects.get(contact=c).level.name, "Партнер")
        call_command("partners_sweep", "--apply", stdout=StringIO())         # повторний прогін нічого не змінює
        self.assertEqual(PartnerStatusHistory.objects.filter(contact=c).count(), 1)

    def test_seed_rules_dry_then_apply(self):
        call_command("partners_seed_rules", stdout=StringIO())
        self.assertEqual(PartnerDiscountRule.objects.count(), 0)
        call_command("partners_seed_rules", "--apply", stdout=StringIO())
        start = self.lv["Старт"]
        self.assertEqual(PartnerDiscountRule.objects.get(level=start, category=self.root).pct, D("15"))
        self.assertEqual(PartnerDiscountRule.objects.get(level=start, category=self.tools).pct, D("10"))
        self.assertEqual(RuleBook().effective(self.p22, start)["pct"], D("7"))  # урізано до 15 п.п. маржі


class DealMarginTests(_Base):
    def test_warning_only_for_partner_deals(self):
        c = self.contact()
        deal = self.deal(c)
        it = DealItem.objects.create(deal=deal, product=self.p66, quantity=1, price=1000, discount_pct=60, cost=340)
        cheap = DealItem.objects.create(deal=deal, product=self.p66, quantity=1, price=450, cost=340)  # знижена ціна
        ok = DealItem.objects.create(deal=deal, product=self.p66, quantity=2, price=1000, discount_pct=15, cost=340)
        r = self.client_owner.get("/api/partners/deals/%s/margin/" % deal.id)
        self.assertEqual(r.data, {"deal_id": deal.id, "is_partner": False})
        PartnerStatus.objects.create(contact=c, level=self.lv["Старт"])
        self.rule("Старт", 15, category=self.root)
        r = self.client_owner.get("/api/partners/deals/%s/margin/" % deal.id)
        rows = {x["item_id"]: x for x in r.data["rows"]}
        self.assertEqual((rows[it.id]["left_pp"], rows[it.id]["below_min"]), (6.0, True))
        # ціну знижено замість знижки: 450 − 340 = 110 від роздрібних 1000 = 11 п.п. < 15 — ловиться так само
        self.assertEqual((rows[cheap.id]["discount_fact_pct"], rows[cheap.id]["left_pp"], rows[cheap.id]["below_min"]),
                         (55.0, 11.0, True))
        self.assertEqual((rows[ok.id]["left_pp"], rows[ok.id]["below_min"]), (51.0, False))
        self.assertEqual(rows[ok.id]["recommended_pct"], 15.0)
        self.assertEqual(r.data["n_below"], 2)
        it.refresh_from_db()
        self.assertEqual(it.discount_pct, D("60"))                          # нічого не змінено — лише попередження
        r = self.client_mgr.get("/api/partners/deals/%s/margin/" % deal.id)
        self.assertIsNone(r.data["rows"][0]["left_pp"])                     # без права собівартості — без цифр маржі
        self.assertTrue(r.data["rows"][0]["below_min"])
