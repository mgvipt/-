from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "0004_contact_owner")]

    operations = [
        migrations.AddField(model_name="contact", name="source",
            field=models.CharField(blank=True, default="", max_length=24, help_text="Звідки клієнт (instagram/site/...)")),
        migrations.AddField(model_name="contact", name="address",
            field=models.CharField(blank=True, default="", max_length=255, help_text="Адреса доставки / місто")),
        migrations.AddField(model_name="contact", name="comment",
            field=models.TextField(blank=True, default="", help_text="Нотатки менеджера про клієнта")),
    ]
