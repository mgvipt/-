import datetime
from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [("finance", "0015_worksession")]
    operations = [migrations.AlterField("transaction", "date", models.DateField(db_index=True, default=datetime.date.today))]
