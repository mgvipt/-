"""Сид РЕАЛЬНОЙ финмодели Wallcov (перенос 1:1 из Cashflow fin_model_articles).
Идемпотентно: очищает таблицу и вставляет актуальные статьи.
    python manage.py seed_finmodel
"""
from django.core.management.base import BaseCommand
from apps.finance.models import FinModelArticle

# (category, name, value, value_type, unit, sort_order) — точная копия из Cashflow
ARTICLES = [
    ("revenue_fund", "Поставщики (закупка)", 48.78, "percent", "%", 10),
    ("revenue_fund", "Логістика", 7.0, "percent", "%", 20),
    ("revenue_fund", "Упаковка", 6.0, "percent", "%", 30),
    ("payment_fee", "Комісія LiqPay", 2.7, "percent", "%", 110),
    ("payment_fee", "Комісія Чекбокс", 0.5, "percent", "%", 120),
    ("payment_fee", "AI-витрати на угоду", 130.0, "fixed_per_deal", "грн/угоду", 130),
    ("variable", "Маркетинг Instagram (Meta-ads)", 0.0, "auto_meta_ads", "грн/міс", 210),
    ("variable", "Маркетинг Facebook (Meta-ads)", 0.0, "auto_meta_ads", "грн/міс", 215),
    ("variable", "ФОТ управління", 49638.0, "fixed_sum_per_month", "грн/міс", 220),
    ("variable", "Упаковка/відгрузка ФОТ", 16546.0, "fixed_sum_per_month", "грн/міс", 230),
    ("variable", "Комісії банку (списання, переказ)", 14891.0, "fixed_sum_per_month", "грн/міс", 240),
    ("fixed", "Оренда салону", 10000.0, "fixed_sum_per_month", "грн/міс", 310),
    ("fixed", "Кредити (повернення тіла)", 60000.0, "fixed_sum_per_month", "грн/міс", 320),
    ("fixed", "ФОТ офіс (склад/менеджер/прибиральниця/бухгалтер)", 52000.0, "fixed_sum_per_month", "грн/міс", 330),
    ("fixed", "Комуналка (салон)", 8600.0, "fixed_sum_per_month", "грн/міс", 340),
    ("fixed", "Звʼязок (Інтернет + телефонія)", 1820.0, "fixed_sum_per_month", "грн/міс", 350),
    ("fixed", "Сервіси / Програми", 29000.0, "fixed_sum_per_month", "грн/міс", 360),
    ("fixed", "Податки", 7640.0, "fixed_sum_per_month", "грн/міс", 370),
    ("fixed", "Транспортні (паливо, поїздки)", 3500.0, "fixed_sum_per_month", "грн/міс", 380),
    ("fixed", "Резерв", 10000.0, "fixed_sum_per_month", "грн/міс", 390),
    ("warehouse_rate", "Тонування", 20.0, "percent", "%", 410),
    ("warehouse_rate", "Відгрузка (за кг)", 1.5, "fixed_per_deal", "грн/кг", 420),
    ("warehouse_rate", "Упаковка до 5 кг", 8.0, "fixed_per_deal", "грн/шт", 430),
    ("warehouse_rate", "Упаковка до 10 кг", 13.0, "fixed_per_deal", "грн/шт", 440),
    ("warehouse_rate", "Упаковка до 20 кг", 20.0, "fixed_per_deal", "грн/шт", 450),
    ("config", "Hard limit знижки (%)", 25.0, "percent", "%", 510),
    ("config", "Знижка без бонусу-маржі від (%)", 15.0, "percent", "%", 520),
]


class Command(BaseCommand):
    help = "Сид реальной финмодели Wallcov (из Cashflow)"

    def handle(self, *args, **opts):
        FinModelArticle.objects.all().delete()
        objs = [FinModelArticle(category=c, name=n, value=v, value_type=vt, unit=u, sort_order=o, active=True)
                for (c, n, v, vt, u, o) in ARTICLES]
        FinModelArticle.objects.bulk_create(objs)
        self.stdout.write(self.style.SUCCESS(f"Финмодель: вставлено {len(objs)} статей (реальные данные Wallcov)"))
