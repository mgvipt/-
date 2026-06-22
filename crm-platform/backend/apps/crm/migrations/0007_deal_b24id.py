from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0006_dealitem_reserved")]
    operations = [
        migrations.AddField(model_name="deal", name="b24_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=20,
                help_text="ID угоди в Бітриксі (для токена Cashflow WC-{b24_id})")),
    ]
