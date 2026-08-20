from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inbox", "0014_channel_echat_whatsapp"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="config",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
