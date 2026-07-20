from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inbox", "0012_alter_teammessage_recipient")]

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
                    ("web", "Web Chat"),
                ],
                max_length=24,
            ),
        ),
    ]
