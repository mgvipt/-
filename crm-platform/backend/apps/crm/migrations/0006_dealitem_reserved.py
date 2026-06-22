from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0005_contact_fields")]
    operations = [
        migrations.AddField(model_name="dealitem", name="reserved",
            field=models.BooleanField(default=False, help_text="Товар зарезервовано під цю сделку")),
    ]
