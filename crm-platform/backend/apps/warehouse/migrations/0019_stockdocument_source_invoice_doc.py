from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warehouse', '0018_shop_site_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockdocument',
            name='source_invoice_doc',
            field=models.IntegerField(blank=True, null=True, help_text='IncomingDoc, з якого створено прихід — щоб відкрити оригінал накладної', verbose_name='ID вхідної накладної-джерела'),
        ),
    ]
