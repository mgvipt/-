# -*- coding: utf-8 -*-
"""Нічний розбір діалогів і тижневий аудит (Олег, 26.09.2026)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "9066_reorder")]

    operations = [
        migrations.CreateModel(
            name="DialogReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(default="daily", max_length=10,
                                          help_text="daily — нічний розбір, weekly — тижневий аудит")),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("summary", models.TextField(blank=True, default="")),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("issues", models.JSONField(blank=True, default=list)),
                ("proposals", models.JSONField(blank=True, default=list)),
                ("cost_usd", models.FloatField(default=0)),
            ],
            options={"ordering": ["-id"]},
        ),
    ]
