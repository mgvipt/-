"""Продажі з сайтів = онлайн (17.09.2026, Олег: «зеркально як в інших воронках, рахуємо як онлайн»).

Було: % з маржі, план, бонус «тест → основне», «Моя ЗП» брали лише «21 Основний продукт» і «22 Тестовий набір»;
оплата у воронці «Лендинг · …» (#66638, 255 ₴) менеджеру не рахувалась.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.crm.models import Contact, Deal, DealItem, Funnel, Stage
from apps.finance.models import Account, Transaction
from apps.payroll import engine
from apps.payroll.models import PayComponent, PayPolicy, PayScheme
from apps.warehouse.models import Product


class SiteFunnelsOnlineTests(TestCase):
    def setUp(self):
        cache.clear()
        self.mgr = get_user_model().objects.create_user("so-mgr", "so@example.test", "x")
        self.main = Funnel.objects.create(name="21 Основний продукт")
        self.test = Funnel.objects.create(name="22 Тестовий набір")
        self.land = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua")
        self.shop = Funnel.objects.create(name="23 Інтернет-магазин wallcov.com.ua")
        self.salon = Funnel.objects.create(name="1.С/Покрытия для стен")
        mk = lambda f: Stage.objects.create(funnel=f, name="Оплату отримано", order=3)
        self.st = {f.id: mk(f) for f in (self.main, self.test, self.land, self.shop, self.salon)}
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": [], "funnels": {
            "online": [self.main.id, self.test.id], "test": [self.test.id], "main": [self.main.id, self.salon.id],
            "salon": [self.salon.id]}}})
        self.acc = Account.objects.create(name="Каса so", kind="cash")
        self.kit = Product.objects.create(name="Galateya — тестовий набір", price=Decimal("255"))
        self.paint = Product.objects.create(name="Galateya 5 кг", price=Decimal("4000"))
        self.contact = Contact.objects.create(first_name="Галина")

    def deal(self, funnel, product, amount, day):
        d = Deal.objects.create(title="d", funnel=funnel, stage=self.st[funnel.id], contact=self.contact, amount=amount, owner=self.mgr)
        DealItem.objects.create(deal=d, product=product, quantity=1, price=Decimal(amount))
        Transaction.objects.create(direction="in", amount=Decimal(amount), amount_uah=Decimal(amount), date=day, deal=d, account=self.acc)
        return d

    def test_policy_and_online_funnels(self):
        pol = engine.policy()
        self.assertTrue({self.land.id, self.shop.id} <= set(pol["funnels"]["site"]))
        self.assertNotIn(self.main.id, pol["funnels"]["site"])
        self.assertTrue({self.land.id, self.shop.id} <= set(pol["funnels"]["online"]))
        # ставка зі старим явним списком [21, 22] — отримує воронки сайтів
        self.assertTrue({self.land.id, self.shop.id} <= set(engine.online_funnels({"funnels": [self.main.id, self.test.id]}, pol)))
        # ставка салону (не онлайн) — без сайтів
        self.assertEqual(engine.online_funnels({"funnels": [self.salon.id]}, pol), [self.salon.id])

    def test_test_or_main_by_items_on_site(self):
        kit = self.deal(self.land, self.kit, 255, date(2026, 9, 5))
        order = self.deal(self.shop, self.paint, 4000, date(2026, 9, 10))
        pol = engine.policy()
        self.assertEqual(engine.deal_kind(kit.id, kit.funnel_id, pol), "test")
        self.assertEqual(engine.deal_kind(order.id, order.funnel_id, pol), "main")
        self.assertTrue(Deal.objects.filter(engine.kind_q("test", pol), id=kit.id).exists())
        self.assertFalse(Deal.objects.filter(engine.kind_q("main", pol), id=kit.id).exists())
        self.assertTrue(Deal.objects.filter(engine.kind_q("main", pol), id=order.id).exists())

    def test_margin_share_and_event_bonus_count_site_sales(self):
        s = PayScheme.objects.create(user=self.mgr, position="Менеджер", valid_from=date(2026, 9, 1), employment="none")
        PayComponent.objects.create(scheme=s, kind="margin_share", params={"funnels": [self.main.id, self.test.id], "pct_to_plan": 10})
        PayComponent.objects.create(scheme=s, kind="event_bonus", params={"tiers": {"fast_days": 30, "min_order": 3000, "fast": 300, "slow": 200, "small": 100}})
        self.deal(self.land, self.kit, 255, date(2026, 9, 5))      # тест-набір з лендингу
        self.deal(self.shop, self.paint, 4000, date(2026, 9, 10))  # основне з магазину
        r = engine.calc(self.mgr, "2026-09")
        margin_line = next(l for l in r["lines"] if l.get("kind") == "margin_share")
        self.assertGreater(margin_line["amount"], 0)   # оплати з сайтів у % з маржі
        event_line = next(l for l in r["lines"] if l.get("kind") == "event_bonus")
        self.assertEqual(event_line["amount"], 300)    # тест (лендинг) → основне (магазин) за 5 днів
