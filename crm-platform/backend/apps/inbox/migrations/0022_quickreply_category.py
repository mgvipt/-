from django.db import migrations, models


class Migration(migrations.Migration):
    """Швидкі відповіді: категорія (група в списку) і «коли використовувати»."""

    dependencies = [("inbox", "0021_landing_submission")]

    operations = [
        migrations.AddField(
            model_name="quickreply",
            name="category",
            field=models.CharField(blank=True, db_index=True, default="", max_length=60,
                                   help_text="Група в списку: «Дожими і повернення з ігнору», «Заперечення»…"),
        ),
        migrations.AddField(
            model_name="quickreply",
            name="when_to_use",
            field=models.TextField(blank=True, default="", help_text="Коли використовувати — підказка менеджеру"),
        ),
    ]
