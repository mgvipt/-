from django.db import migrations

# Дефолтные статьи финмодели (Олег редактирует в Налаштування фінмоделі).
# Значения — стартовые по методологии Cashflow/ATM; реальные цифры владелец вписывает сам.
DEFAULTS = [
    # фонди виручки (% з виручки) — формируют прямые расходы
    ("revenue_fund", "Постачальники (собівартість)", 48.78, "percent", "%", 1),
    ("revenue_fund", "Логістика / доставка", 7, "percent", "%", 2),
    ("revenue_fund", "Упаковка", 6, "percent", "%", 3),
    # комісія еквайрингу (₴/угода)
    ("payment_fee", "Комісія еквайрингу (середня)", 50, "fixed_per_deal", "₴/угода", 1),
    # перемінні (% від маржі) — для ATM-формули
    ("variable", "Реклама / маркетинг", 10, "percent", "% маржі", 1),
    ("variable", "Податки", 5, "percent", "% маржі", 2),
    ("variable", "Резерв", 3, "percent", "% маржі", 3),
    # постійні витрати (₴/міс)
    ("fixed", "Оренда", 12000, "fixed_sum_per_month", "₴/міс", 1),
    ("fixed", "Офіс / звʼязок / сервіси", 8000, "fixed_sum_per_month", "₴/міс", 2),
    ("fixed", "CRM та ПЗ", 6000, "fixed_sum_per_month", "₴/міс", 3),
    # УПР обов'язкові (входять у ТБ)
    ("upr_cat2", "ФОП виробництво (оклади)", 40000, "fixed_sum_per_month", "₴/міс", 1),
    ("upr_cat2", "ФОП офіс/менеджмент", 30000, "fixed_sum_per_month", "₴/міс", 2),
    # config
    ("config", "Середня к-сть угод/міс (для ТБ)", 100, "percent", "угод", 1),
    ("config", "Націнка цілі понад ТБ", 30, "percent", "%", 2),
]


def seed(apps, schema_editor):
    Art = apps.get_model("finance", "FinModelArticle")
    for cat, name, value, vt, unit, order in DEFAULTS:
        Art.objects.get_or_create(category=cat, name=name,
            defaults={"value": value, "value_type": vt, "unit": unit, "sort_order": order, "active": True})


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("finance", "0002_finmodelarticle")]
    operations = [migrations.RunPython(seed, unseed)]
