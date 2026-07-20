from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9029_zamerproject")]
    operations = [
        migrations.AddField(
            model_name="contact",
            name="default_purchase_category",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text="finance.Category — підставляється при проведенні накладної цього постачальника (фонд/напрямок тягнуться з категорії)",
                verbose_name="Категорія закупівлі за замовчуванням"),
        ),
    ]
