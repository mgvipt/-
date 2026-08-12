from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "9040_changelog_i18n")]

    operations = [
        migrations.AddField(
            model_name="funnel",
            name="is_archive",
            field=models.BooleanField(default=False, help_text="Архівна воронка — сделки для історії, НЕ вантажаться на дошку авто (тільки пошук)"),
        ),
    ]
