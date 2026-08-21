from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inbox", "0015_conversation_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="meta_external_id",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.AlterField(
            model_name="message",
            name="status",
            field=models.CharField(
                choices=[
                    ("sent", "Надіслано"),
                    ("delivered", "Доставлено"),
                    ("read", "Прочитано"),
                    ("failed", "Не доставлено"),
                    ("window_risk", "Вікно закрите — міг не дійти"),
                ],
                default="sent",
                help_text="Статус доставки вихідного",
                max_length=12,
            ),
        ),
    ]
