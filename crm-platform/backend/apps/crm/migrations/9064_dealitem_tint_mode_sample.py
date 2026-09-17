# 17.09.2026 (Олег): викраски — індивідуальний колір (доплата). Лише нові варіанти вибору; у базі нічого не змінюється.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "9063_dealitem_tint_mode")]

    operations = [
        migrations.AlterField(
            model_name="dealitem",
            name="tint_mode",
            field=models.CharField(blank=True, default="", max_length=10,
                                   choices=[("", "Колір з каталогу"), ("ind", "Індивідуальний колір"),
                                            ("rich", "Насичений колір"), ("auto_ind", "Доплата: індивідуальний колір"),
                                            ("auto_rich", "Доплата: насичений колір"),
                                            ("s_ind", "Викраска: індивідуальний колір"),
                                            ("auto_s_ind", "Доплата: індивідуальний колір викраски")],
                                   help_text="Тонування тест-набору (галочка в угоді)"),
        ),
    ]
