from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9055_kb")]
    operations = [
        migrations.AddField(
            model_name="deal", name="area_m2",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True,
                help_text="Площа стін для авто-розрахунку кількості матеріалу", verbose_name="Площа, м²"),
        ),
    ]
