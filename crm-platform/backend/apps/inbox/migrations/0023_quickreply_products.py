import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """17.09.2026: швидкі відповіді з номенклатури — привʼязані позиції, папка-джерело, сімʼя товару;
    папка номенклатури → розділ швидких відповідей. Лише нові поля й таблиця, дані не змінюються."""

    dependencies = [
        ("inbox", "0022_quickreply_category"),
        ("warehouse", "0026_washed_samples"),
    ]

    operations = [
        migrations.AddField(
            model_name="quickreply",
            name="products",
            field=models.ManyToManyField(blank=True, related_name="quick_replies", to="warehouse.product"),
        ),
        migrations.AddField(
            model_name="quickreply",
            name="product_folder",
            field=models.ForeignKey(blank=True, help_text="Папка номенклатури, з якої створено відповідь", null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name="quick_replies",
                                    to="warehouse.productcategory"),
        ),
        migrations.AddField(
            model_name="quickreply",
            name="product_key",
            field=models.CharField(blank=True, default="", help_text="Сімʼя товару в папці: група варіантів магазину або p<id>",
                                   max_length=80),
        ),
        migrations.AddField(
            model_name="quickreply",
            name="auto_hidden",
            field=models.BooleanField(default=False, help_text="Сховано автоматично: у папці не лишилось активних позицій"),
        ),
        migrations.AddConstraint(
            model_name="quickreply",
            constraint=models.UniqueConstraint(condition=models.Q(("product_key", ""), _negated=True),
                                               fields=("product_folder", "product_key"),
                                               name="quickreply_folder_product_key_uniq"),
        ),
        migrations.CreateModel(
            name="QuickReplyFolder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(help_text="Розділ у швидких відповідях: «Тест-набори з цінами»", max_length=60)),
                ("kind", models.CharField(choices=[("test_set", "Тест-набори (варіанти з дощечкою / тонуванням)"),
                                                   ("sample", "Викраски"), ("product", "Товари")],
                                          default="product", max_length=10)),
                ("when_to_use", models.TextField(blank=True, default="", help_text="Підказка «коли» для нових відповідей")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("folder", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="quick_reply_link",
                                                to="warehouse.productcategory")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
