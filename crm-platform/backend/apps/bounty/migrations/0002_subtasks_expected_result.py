"""Біржа задач v2 (15.09.2026): «Навіщо», «Кінцевий результат», підзадачі; знімок і відмітки підзадач у взятій задачі;
відділ «Найм» і нова назва відділу «Салон». Лише додавання полів з порожнім значенням — наявні дані не змінюються."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bounty", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="taskcategory",
            name="department",
            field=models.CharField(choices=[("marketing", "Маркетинг / SMM"), ("sales", "Продажі"), ("warehouse", "Склад"), ("salon", "Офлайн-магазин (салон)"), ("objects", "Обʼєкти"), ("content", "Контент / сайт"), ("ai_crm", "ІІ і CRM"), ("hr", "Найм"), ("office", "Офіс")], db_index=True, max_length=16),
        ),
        migrations.AddField(
            model_name="taskoffer",
            name="why",
            field=models.CharField(blank=True, default="", help_text="Навіщо це бізнесу — один рядок", max_length=255),
        ),
        migrations.AddField(
            model_name="taskoffer",
            name="expected_result",
            field=models.TextField(blank=True, default="", help_text="Кінцевий результат, який можна виміряти («50 товарів мають вагу»)"),
        ),
        migrations.AddField(
            model_name="taskoffer",
            name="subtasks",
            field=models.JSONField(blank=True, default=list, help_text="Підзадачі: [{title, how}] — що зробити і як, по порядку"),
        ),
        migrations.AddField(
            model_name="taskclaim",
            name="subtasks",
            field=models.JSONField(blank=True, default=list, help_text="Знімок підзадач задачі на момент «Беру» — зміна прайсу не зсуває відмітки"),
        ),
        migrations.AddField(
            model_name="taskclaim",
            name="subtasks_done",
            field=models.JSONField(blank=True, default=list, help_text="Номери (з 0) виконаних підзадач"),
        ),
    ]
