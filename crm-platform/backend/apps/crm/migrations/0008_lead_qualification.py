from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0007_deal_b24id"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="qualification",
            field=models.JSONField(blank=True, default=dict,
                help_text="Анкета виявлення потреби (тип приміщення, площа, матеріал, бюджет тощо)"),
        ),
    ]
