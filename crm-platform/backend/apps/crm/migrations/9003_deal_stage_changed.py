from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [("crm", "9002_dealitem_discount")]
    operations = [migrations.AddField("deal", "stage_changed_at", models.DateTimeField(blank=True, null=True))]
