from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "9051_contact_advance_adjust")]

    operations = [
        migrations.AddField(model_name="contact", name="expense_adjust",
                            field=models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Коригування витрат")),
        migrations.AddField(model_name="contact", name="expense_adjust_note",
                            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Причина коригування витрат")),
    ]
