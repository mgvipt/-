from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9036_deal_parent")]
    operations = [
        migrations.AddField(
            model_name="contact",
            name="payment_purpose",
            field=models.CharField(blank=True, default="", max_length=200,
                help_text="Своє призначення для оплати цьому постачальнику через ФОП. Плейсхолдери {номер} і {дата} підставляться з рахунку. Порожньо = «Оплата рахунку №… від …»",
                verbose_name="Призначення платежу (шаблон)"),
        ),
    ]
