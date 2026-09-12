"""Сид РЕАЛЬНОЙ финмодели Wallcov (полная структура фондов из Finmap ФВ/ФМ/ФСКД).

Захист (12.09.2026): раніше команда мовчки видаляла ВСІ статті (ЗП-ставки, ставки складу,
розподіли фондів каскадом) і відвʼязувала від них операції журналу. Тепер:
    python manage.py seed_finmodel                 # порожня таблиця → створює; заповнена → ВІДМОВА, нічого не змінює
    python manage.py seed_finmodel --dry-run       # лише показати, що буде створено / видалено
    python manage.py seed_finmodel --missing-only  # додати тільки відсутні (за code, інакше категорія+назва), наявні не чіпає
    python manage.py seed_finmodel --force-reset --i-understand   # НЕБЕЗПЕЧНО: видалити все і створити заново
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
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

# Машинні коди статей, які вже живуть у проді під іншими назвами (склад рахує ЗП по code).
# За ними --missing-only впізнає перейменовану статтю і не створює дубль.
CODES = {
    ("warehouse_rate", "Тонування"): "WH_TINT_PCT",
    ("warehouse_rate", "Відгрузка (за кг)"): "WH_RATE_KG",
    ("warehouse_rate", "Упаковка до 5 кг"): "WH_PACK_5",
    ("warehouse_rate", "Упаковка до 10 кг"): "WH_PACK_10",
    ("warehouse_rate", "Упаковка до 20 кг"): "WH_PACK_20",
}


def _article(c, n, v, vt, u, o):
    return FinModelArticle(category=c, name=n, value=v, value_type=vt, unit=u, sort_order=o, active=True,
                           code=CODES.get((c, n), ""))


def _missing():
    """Рядки сиду, яких ще немає в БД: за code (якщо є), інакше за категорією+назвою."""
    codes = set(FinModelArticle.objects.exclude(code="").values_list("code", flat=True))
    names = set(FinModelArticle.objects.values_list("category", "name"))
    return [row for row in ARTICLES
            if not (CODES.get(row[:2]) in codes or row[:2] in names)]


def _reset_impact():
    """Що знищить повне перестворення: статті + усе, що на них посилається (каскад або SET_NULL)."""
    lines = [f"статті фінмоделі: {FinModelArticle.objects.count()} — будуть ВИДАЛЕНІ"]
    for rel in FinModelArticle._meta.get_fields(include_hidden=True):
        if not (rel.auto_created and not rel.concrete and (rel.one_to_many or rel.one_to_one)):
            continue
        if rel.related_model is FinModelArticle:
            continue  # підфонди — це ті самі статті
        n = rel.related_model._base_manager.filter(**{f"{rel.field.name}__isnull": False}).count()
        if n:
            what = "будуть ВИДАЛЕНІ (каскад)" if rel.on_delete is models.CASCADE else "втратять привʼязку до статті"
            lines.append(f"{rel.related_model._meta.label}.{rel.field.name}: {n} — {what}")
    return lines


class Command(BaseCommand):
    help = "Сид повної финмодели Wallcov (фонди ФВ/ФМ/ФСКД з Finmap). Заповнену фінмодель без прапорців НЕ чіпає."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Лише показати, що буде створено/видалено; нічого не змінювати")
        parser.add_argument("--missing-only", action="store_true",
                            help="Додати тільки відсутні статті; наявні не змінювати і не видаляти")
        parser.add_argument("--force-reset", action="store_true",
                            help="НЕБЕЗПЕЧНО: видалити ВСІ статті і створити заново (лише разом з --i-understand)")
        parser.add_argument("--i-understand", action="store_true",
                            help="Підтвердження для --force-reset")

    def handle(self, *args, **opts):
        dry, force, missing_only = opts["dry_run"], opts["force_reset"], opts["missing_only"]
        if force != opts["i_understand"]:
            raise CommandError("--force-reset працює лише разом з --i-understand. Нічого не змінено.")
        if force and missing_only:
            raise CommandError("--force-reset і --missing-only несумісні. Нічого не змінено.")
        existing = FinModelArticle.objects.count()
        missing = _missing()
        out = self.stdout.write

        if dry:
            out("DRY-RUN — нічого не змінено.")
            if force:
                out("--force-reset --i-understand видалить:")
                for line in _reset_impact():
                    out(f"  - {line}")
                out(f"і створить заново {len(ARTICLES)} статей зі списку сиду "
                    "(ручні значення, ЗП-ставки та статті поза списком зникнуть).")
                return
            if existing and not missing_only:
                out(f"Без прапорців: ВІДМОВА — фінмодель вже заповнена ({existing} статей).")
            out(f"{'--missing-only створить' if existing else 'Буде створено'} {len(missing)} статей:")
            for c, n, *_ in missing:
                out(f"  + {c}: {n}")
            return

        if force:
            impact = _reset_impact()
            with transaction.atomic():
                FinModelArticle.objects.all().delete()
                FinModelArticle.objects.bulk_create([_article(*row) for row in ARTICLES])
            for line in impact:
                out(f"  - {line}")
            out(self.style.WARNING(f"Финмодель ПЕРЕСТВОРЕНО: {len(ARTICLES)} статей (повна структура фондів)"))
            return

        if existing and not missing_only:
            raise CommandError(
                f"Фінмодель вже заповнена ({existing} статей) — нічого не змінено. "
                f"Подивитись план: --dry-run. Додати {len(missing)} відсутніх: --missing-only. "
                "Повне перестворення (видалить усі статті): --force-reset --i-understand.")

        FinModelArticle.objects.bulk_create([_article(*row) for row in missing])
        out(self.style.SUCCESS(f"Финмодель: створено {len(missing)} статей, наявні {existing} не змінено"))
