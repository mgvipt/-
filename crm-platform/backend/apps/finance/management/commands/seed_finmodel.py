"""Сид РЕАЛЬНОЙ финмодели Wallcov (полная структура фондов из Finmap ФВ/ФМ/ФСКД).
Идемпотентно: очищает таблицу и вставляет статьи.
    python manage.py seed_finmodel
"""
from django.core.management.base import BaseCommand
from apps.finance.models import FinModelArticle

# (category, name, value, value_type, unit, sort_order). value=0 → владелец впишет норматив.
ARTICLES = [
    # ФВ — фонди виручки (% з кожної угоди)
    ("revenue_fund", "Постачальники (закупка)", 48.78, "percent", "%", 10),
    ("revenue_fund", "Логістика / доставка", 7.0, "percent", "%", 20),
    ("revenue_fund", "Упаковка (матеріали)", 6.0, "percent", "%", 30),
    ("revenue_fund", "ФОТ % продажу (комісія менеджера)", 0, "percent", "%", 40),
    ("revenue_fund", "Дивіденди майстрам", 0, "percent", "%", 50),
    # ВИТРАТИ НА ОБРОБКУ (на угоду)
    ("payment_fee", "Комісія LiqPay", 2.7, "percent", "%", 110),
    ("payment_fee", "Комісія Чекбокс", 0.5, "percent", "%", 120),
    ("payment_fee", "AI-витрати на угоду", 130.0, "fixed_per_deal", "грн/угоду", 130),
    # ФМ — перемінні (грн/міс)
    ("variable", "Таргет-бюджет Instagram (Meta-ads)", 0.0, "auto_meta_ads", "грн/міс", 210),
    ("variable", "Таргет-бюджет Facebook (Meta-ads)", 0.0, "auto_meta_ads", "грн/міс", 215),
    ("variable", "Маркетинг СММ (контент, копірайт, реклама)", 0, "fixed_sum_per_month", "грн/міс", 218),
    ("variable", "ФОТ управління", 49638.0, "fixed_sum_per_month", "грн/міс", 220),
    ("variable", "ФОТ упаковка/тонування/відгрузка", 16546.0, "fixed_sum_per_month", "грн/міс", 230),
    ("variable", "Списання відсотків + комісії банку", 14891.0, "fixed_sum_per_month", "грн/міс", 240),
    # ФМ — постійні (грн/міс)
    ("fixed", "Оренда салону", 10000.0, "fixed_sum_per_month", "грн/міс", 310),
    ("fixed", "Кредити (повернення тіла)", 60000.0, "fixed_sum_per_month", "грн/міс", 320),
    ("fixed", "ФОТ офіс (склад/менеджер/прибиральниця/бухгалтер)", 52000.0, "fixed_sum_per_month", "грн/міс", 330),
    ("fixed", "Комуналка (салон)", 8600.0, "fixed_sum_per_month", "грн/міс", 340),
    ("fixed", "Звʼязок (Інтернет + телефонія)", 1820.0, "fixed_sum_per_month", "грн/міс", 350),
    ("fixed", "Сервіси / Програми", 29000.0, "fixed_sum_per_month", "грн/міс", 360),
    ("fixed", "Податки", 7640.0, "fixed_sum_per_month", "грн/міс", 370),
    ("fixed", "Транспортні (паливо, поїздки)", 3500.0, "fixed_sum_per_month", "грн/міс", 380),
    ("fixed", "Резерв", 10000.0, "fixed_sum_per_month", "грн/міс", 390),
    # ФСКД — фонд розвитку (грн/міс)
    ("skd", "Обслуговування обладнання / інструментів", 0, "fixed_sum_per_month", "грн/міс", 610),
    ("skd", "Фонд обладнання", 0, "fixed_sum_per_month", "грн/міс", 620),
    ("skd", "Навчання", 0, "fixed_sum_per_month", "грн/міс", 630),
    ("skd", "Господарські витрати", 0, "fixed_sum_per_month", "грн/міс", 640),
    ("skd", "Життєдіяльність офісу (вода, кава, канцелярія)", 0, "fixed_sum_per_month", "грн/міс", 650),
    # Склад — ставки
    ("warehouse_rate", "Тонування", 20.0, "percent", "%", 410),
    ("warehouse_rate", "Відгрузка (за кг)", 1.5, "fixed_per_deal", "грн/кг", 420),
    ("warehouse_rate", "Упаковка до 5 кг", 8.0, "fixed_per_deal", "грн/шт", 430),
    ("warehouse_rate", "Упаковка до 10 кг", 13.0, "fixed_per_deal", "грн/шт", 440),
    ("warehouse_rate", "Упаковка до 20 кг", 20.0, "fixed_per_deal", "грн/шт", 450),
    # Конфіг
    ("config", "Hard limit знижки (%)", 25.0, "percent", "%", 510),
    ("config", "Знижка без бонусу-маржі від (%)", 15.0, "percent", "%", 520),
]


class Command(BaseCommand):
    help = "Сид повної финмодели Wallcov (фонди ФВ/ФМ/ФСКД з Finmap)"

    def handle(self, *args, **opts):
        FinModelArticle.objects.all().delete()
        FinModelArticle.objects.bulk_create([
            FinModelArticle(category=c, name=n, value=v, value_type=vt, unit=u, sort_order=o, active=True)
            for (c, n, v, vt, u, o) in ARTICLES])
        self.stdout.write(self.style.SUCCESS(f"Финмодель: {len(ARTICLES)} статей (повна структура фондів)"))
