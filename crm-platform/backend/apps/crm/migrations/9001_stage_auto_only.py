from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0013_automationrule")]
    operations = [
        migrations.AddField("stage", "auto_only", models.BooleanField(default=False)),
    ]
