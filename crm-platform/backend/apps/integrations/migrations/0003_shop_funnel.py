from django.db import migrations


SHOP_FUNNEL_NAME = "23 Інтернет-магазин"

STAGES = [
    ("Нове замовлення з сайту", "#94a3b8", False, False),
    ("Розрахунок здійснено (КП)", "#3b82f6", False, False),
    ("Домовились про оплату", "#6366f1", False, False),
    ("Оплату отримано", "#8b5cf6", False, False),
    ("Заброньовано", "#0ea5e9", False, False),
    ("Відвантаження", "#f59e0b", False, False),
    ("Тонування", "#10b981", False, False),
    ("Пакування", "#14b8a6", False, False),
    ("НП_ТТН створена", "#16a34a", False, False),
    ("НП_Відправленя в Мог.-Под.", "#ef4444", False, False),
    ("НП_В дорозі", "#94a3b8", False, False),
    ("НП_Прибув на відділення", "#3b82f6", False, False),
    ("НП_На відділення 3 дні", "#6366f1", False, False),
    ("Отримано", "#8b5cf6", False, False),
    ("Успішна угода", "#0ea5e9", True, False),
    ("Скасовано після оплати", "#f59e0b", False, True),
    ("Отказался назвать причину", "#10b981", False, True),
    ("Пропущенные", "#14b8a6", False, True),
    ("НЕ АКТУАЛЬНО", "#16a34a", False, True),
    ("Игнор", "#ef4444", False, True),
    ("Отказался", "#94a3b8", False, True),
    ("Дубляж", "#3b82f6", False, True),
    ("Уже купил", "#6366f1", False, True),
    ("Дорого", "#8b5cf6", False, True),
    ("Спам", "#0ea5e9", False, True),
    ("Отказ", "#f59e0b", False, True),
]


def create_shop_funnel(apps, schema_editor):
    Funnel = apps.get_model("crm", "Funnel")
    Stage = apps.get_model("crm", "Stage")
    source = Funnel.objects.filter(name="21 Основний продукт").first()
    next_order = max(Funnel.objects.values_list("order", flat=True), default=0) + 1
    funnel, _ = Funnel.objects.get_or_create(
        name=SHOP_FUNNEL_NAME,
        defaults={"is_lead_funnel": False, "order": next_order},
    )

    for order, (name, color, is_won, is_lost) in enumerate(STAGES):
        Stage.objects.get_or_create(
            funnel=funnel,
            name=name,
            defaults={"order": order, "color": color, "is_won": is_won, "is_lost": is_lost},
        )

    if source is None:
        return

    for model_name, relation in (("Role", "funnels"), ("Department", "funnels"), ("User", "extra_funnels")):
        model = apps.get_model("accounts", model_name)
        for obj in model.objects.filter(**{relation: source}).distinct():
            getattr(obj, relation).add(funnel)


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0002_shoporderimport"),
    ]

    operations = [
        migrations.RunPython(create_shop_funnel, migrations.RunPython.noop),
    ]
