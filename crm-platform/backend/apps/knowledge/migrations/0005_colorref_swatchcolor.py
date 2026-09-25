# -*- coding: utf-8 -*-
# 25.09.2026: довідник кольорів RAL/NCS + середній колір наших образків.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("knowledge", "0004_alter_knowledgesettings_ai_max_per_day_and_more")]

    operations = [
        migrations.CreateModel(
            name="ColorRef",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("system", models.CharField(choices=[("ral", "RAL Classic"), ("ncs", "NCS")], db_index=True, max_length=4)),
                ("code", models.CharField(db_index=True, max_length=32)),
                ("name_uk", models.CharField(blank=True, default="", max_length=80)),
                ("name_ru", models.CharField(blank=True, default="", max_length=80)),
                ("name_en", models.CharField(blank=True, default="", max_length=80)),
                ("hex", models.CharField(max_length=7)),
                ("lab_l", models.FloatField()),
                ("lab_a", models.FloatField()),
                ("lab_b", models.FloatField()),
            ],
            options={"unique_together": {("system", "code")}},
        ),
        migrations.AddIndex(
            model_name="colorref",
            index=models.Index(fields=["system", "code"], name="knowledge_c_system_25b2cf_idx"),
        ),
        migrations.CreateModel(
            name="SwatchColor",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_id", models.IntegerField(help_text="MediaLibraryItem", unique=True)),
                ("material", models.CharField(db_index=True, max_length=80)),
                ("color_code", models.CharField(db_index=True, max_length=40)),
                ("hex", models.CharField(max_length=7)),
                ("lab_l", models.FloatField()),
                ("lab_a", models.FloatField()),
                ("lab_b", models.FloatField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
