"""Чотири рівні за рішенням Олега (14.09.2026): пороги оплаченого обороту і частки маржі для підказки ATM.
Лише створює, якщо рівнів ще немає; змінюються потім на екрані «Партнери → Рівні і налаштування»."""
from decimal import Decimal

from django.db import migrations

LEVELS = [
    ("Старт", 1, "0", "0.25", "#64748b"),
    ("Партнер", 2, "25000", "0.40", "#2563eb"),
    ("Золото", 3, "75000", "0.50", "#ca8a04"),
    ("Дилер", 4, "200000", "0.60", "#7c3aed"),
]


def seed(apps, schema_editor):
    Level = apps.get_model("partners", "PartnerLevel")
    if Level.objects.exists():
        return
    for name, order, threshold, share, color in LEVELS:
        Level.objects.create(name=name, order=order, threshold_uah=Decimal(threshold),
                             margin_share=Decimal(share), color=color)


class Migration(migrations.Migration):

    dependencies = [
        ("partners", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
