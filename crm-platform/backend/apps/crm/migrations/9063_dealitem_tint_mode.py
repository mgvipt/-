# 16.09.2026 (Олег): галочка тонування тест-набору в угоді. Лише нове поле — нічого іншого не чіпаємо.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "9062_lead_source_salon")]

    operations = [
        migrations.AddField(
            model_name="dealitem",
            name="tint_mode",
            field=models.CharField(blank=True, default="", max_length=10,
                                   choices=[("", "Колір з каталогу"), ("ind", "Індивідуальний колір"),
                                            ("rich", "Насичений колір"), ("auto_ind", "Доплата: індивідуальний колір"),
                                            ("auto_rich", "Доплата: насичений колір")],
                                   help_text="Тонування тест-набору (галочка в угоді)"),
        ),
    ]
