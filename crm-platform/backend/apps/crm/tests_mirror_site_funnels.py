"""Воронки сайтів = стадії робочих онлайн-воронок (17.09.2026).

Кейс: #66638 (лендинг) оплачено 255 ₴ через LiqPay, а сделка поїхала на «Подбор 3 вариантов»
(автоматика шукає «Оплату отримано» за назвою, не знайшла і взяла стадію №3) — склад задачу не отримав.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Role
from apps.crm.models import Deal, DealItem, Funnel, Payment, PayLink, Stage
from apps.warehouse.models import Product
from apps.warehouse.models import WarehouseJob

TPL = ["Данні для розрахунку", "Розрахунок здійснено (КП)", "Домовились про оплату", "Оплату отримано",
       "Відвантаження", "НП_ТТН створена", "Отримано", "Успішна угода", "НЕ АКТУАЛЬНО"]
OLD = ["Новая заявка", "Первый контакт", "Фото и параметры получены", "Подбор 3 вариантов",
       "Расчёт отправлен", "Ожидаем оплату", "Заказ оплачен", "Сделка успешна", "Не реализовано"]


class MirrorSiteFunnelsTests(TestCase):
    def setUp(self):
        self.main = Funnel.objects.create(name="21 Основний продукт")
        self.test = Funnel.objects.create(name="22 Тестовий набір")
        for f in (self.main, self.test):
            for i, n in enumerate(TPL):
                Stage.objects.create(funnel=f, name=n, order=i, auto_only=i < 7,
                                     is_won=n == "Успішна угода", is_lost=n == "НЕ АКТУАЛЬНО")
        self.land = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua")
        self.old = {n: Stage.objects.create(funnel=self.land, name=n, order=i,
                                            is_won=n == "Сделка успешна", is_lost=n == "Не реализовано")
                    for i, n in enumerate(OLD)}
        self.shop = Funnel.objects.create(name="23 Інтернет-магазин wallcov.com.ua")
        Stage.objects.create(funnel=self.shop, name="Нове замовлення з сайту", order=0)
        for i, n in enumerate(TPL[1:], start=1):
            Stage.objects.create(funnel=self.shop, name=n, order=i, is_won=n == "Успішна угода", is_lost=n == "НЕ АКТУАЛЬНО")
        self.role = Role.objects.create(name="Менеджер (mirror)", stage_view_all=[x.id for x in self.old.values()])
        self.prod = Product.objects.create(name="Galateya — тестовий набір", price=Decimal("255"))
        mk = lambda st, amount=0: Deal.objects.create(title="d", funnel=self.land, stage=self.old[st], amount=Decimal(amount))
        self.paid = mk("Подбор 3 вариантов", 255)
        DealItem.objects.create(deal=self.paid, product=self.prod, quantity=1, price=Decimal("255"))
        Payment.objects.create(deal=self.paid, amount=Decimal("255"), is_paid=True)
        self.link = mk("Фото и параметры получены", 335)
        PayLink.objects.create(code="tst1", deal=self.link, target="https://x")
        self.calc = mk("Первый контакт", 816)
        DealItem.objects.create(deal=self.calc, product=self.prod, quantity=1, price=Decimal("816"))
        self.bare = mk("Новая заявка")
        self.won = mk("Сделка успешна", 100)
        self.lost = mk("Не реализовано")

    def run_cmd(self, *args):
        out = StringIO()
        call_command("mirror_site_funnels", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        self.run_cmd()
        self.assertEqual(sorted(self.land.stages.values_list("name", flat=True)), sorted(OLD))
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.stage.name, "Подбор 3 вариантов")

    def test_apply_mirrors_stages_and_moves_deals_by_facts(self):
        self.run_cmd("--apply")
        self.assertEqual(list(self.land.stages.order_by("order").values_list("name", flat=True)), TPL)
        st = lambda d: Deal.objects.get(id=d.id).stage.name
        self.assertEqual(st(self.paid), "Оплату отримано")
        self.assertEqual(st(self.link), "Домовились про оплату")
        self.assertEqual(st(self.calc), "Розрахунок здійснено (КП)")
        self.assertEqual(st(self.bare), "Данні для розрахунку")
        self.assertEqual(st(self.won), "Успішна угода")
        self.assertEqual(st(self.lost), "НЕ АКТУАЛЬНО")
        self.assertTrue(WarehouseJob.objects.filter(deal=self.paid).exists())
        self.assertEqual(WarehouseJob.objects.filter(deal=self.link).count(), 0)
        self.assertTrue(Stage.objects.get(funnel=self.land, name="Оплату отримано").auto_only)
        # магазин: перша стадія зі своєю назвою лишилась, інші — як у зразку
        self.assertEqual(list(self.shop.stages.order_by("order").values_list("name", flat=True)),
                         ["Нове замовлення з сайту"] + TPL[1:])
        # «бачити всі сделки на стадії» у ролі Менеджер переїхало на нові стадії лендингу
        role = Role.objects.get(id=self.role.id)
        land_ids = set(self.land.stages.values_list("id", flat=True))
        self.assertEqual(set(role.stage_view_all), land_ids)
        # робочі воронки не змінено
        for f in (self.main, self.test):
            self.assertEqual(list(f.stages.order_by("order").values_list("name", flat=True)), TPL)
        # повторний запуск нічого не робить
        self.assertIn("перенесено сделок: 0", self.run_cmd("--apply"))

    def test_limit_moves_only_n(self):
        self.run_cmd("--apply", "--limit", "2")
        moved = Deal.objects.filter(funnel=self.land, stage__name__in=TPL).count()
        self.assertEqual(moved, 2)
        self.run_cmd("--apply")
        self.assertEqual(Deal.objects.filter(funnel=self.land, stage__name__in=TPL).count(), 6)
        self.assertEqual(sorted(self.land.stages.values_list("name", flat=True)), sorted(TPL))
