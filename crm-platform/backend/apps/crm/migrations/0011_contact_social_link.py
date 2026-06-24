from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0010_deal_qualification_card_fields")]
    operations = [
        migrations.AddField(model_name="contact", name="social_link",
            field=models.CharField(blank=True, default="", max_length=300)),
    ]
