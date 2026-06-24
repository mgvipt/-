from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("telephony", "0003_callrequest")]
    operations = [
        migrations.AddField(model_name="call", name="line",
            field=models.CharField(blank=True, max_length=60, help_text="SIM-лінія, напр. 803 · Салон")),
    ]
