from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inbox", "0016_message_statuses_edits"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="is_followup",
            field=models.BooleanField(default=False, help_text="Дожим — повідомлення-нагадування клієнту, який замовк"),
        ),
    ]
