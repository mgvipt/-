from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("telephony", "0005_ringingcall")]
    operations = [
        migrations.AddField(model_name="call", name="transcript", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="call", name="analyzed", field=models.BooleanField(default=False)),
    ]
