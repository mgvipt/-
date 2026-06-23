from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0008_lead_qualification"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="card_fields",
            field=models.JSONField(blank=True, default=list,
                help_text="Кастомні поля/блоки картки (як у Бітриксі): [{label, value}]"),
        ),
    ]
