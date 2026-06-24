from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9001_stage_auto_only")]
    operations = [
        migrations.AddField("dealitem", "discount_pct", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
    ]
