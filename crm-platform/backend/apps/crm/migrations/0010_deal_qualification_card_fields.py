from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0009_lead_card_fields"),
    ]

    operations = [
        migrations.AddField(model_name="deal", name="qualification",
            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="deal", name="card_fields",
            field=models.JSONField(blank=True, default=list)),
    ]
