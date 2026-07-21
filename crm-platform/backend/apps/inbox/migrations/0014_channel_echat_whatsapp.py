from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inbox", "0013_alter_channel_kind")]

    operations = [
        migrations.AlterField(
            model_name="channel",
            name="kind",
            field=models.CharField(
                choices=[
                    ("telegram", "Telegram"),
                    ("viber", "Viber"),
                    ("instagram", "Instagram"),
                    ("facebook", "Facebook"),
                    ("whatsapp", "WhatsApp"),
                    ("google_business", "Google Бизнес"),
                    ("echat_whatsapp", "WhatsApp (e-chat)"),
                    ("web", "Web Chat"),
                ],
                max_length=24,
            ),
        ),
    ]
