from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9039_contact_links_extra"),
    ]

    operations = [
        migrations.AddField(
            model_name="changelogentry",
            name="section_key",
            field=models.CharField(blank=True, db_index=True, default="", max_length=24,
                                   help_text="Ключ категорії: finance/warehouse/clients/sales/delivery/shop/telephony/general"),
        ),
        migrations.AddField(
            model_name="changelogentry",
            name="title_uk",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="changelogentry",
            name="title_ru",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="changelogentry",
            name="body_uk",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="changelogentry",
            name="body_ru",
            field=models.TextField(blank=True, default=""),
        ),
    ]
