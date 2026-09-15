from django.db import migrations, models

SOURCES = [
    ("telegram", "Telegram"), ("viber", "Viber"), ("instagram", "Instagram"),
    ("facebook", "Facebook"), ("whatsapp", "WhatsApp"), ("call", "Звонок"),
    ("google_business", "Google Бизнес"), ("other", "Другое"),
    ("site", "Сайт wallcovdec"), ("wholesale", "Опт / дилери"),
    ("designers", "Дизайнери / прораби"), ("tiktok", "TikTok"),
    ("salon", "Салон (офлайн)"),
]


class Migration(migrations.Migration):
    """15.09.2026 (Олег): джерело «Салон (офлайн)» у лідах і угодах. Змінюються лише варіанти вибору —
    таблиці в базі не змінюються (Postgres не отримує жодної команди)."""

    dependencies = [
        ("crm", "9061_lead_quality"),
    ]

    operations = [
        migrations.AlterField(model_name="lead", name="source",
                              field=models.CharField(choices=SOURCES, default="other", max_length=24)),
        migrations.AlterField(model_name="deal", name="source",
                              field=models.CharField(choices=SOURCES, default="other", max_length=24)),
    ]
