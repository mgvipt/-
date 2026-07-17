from django.db import migrations, models
from django.contrib.postgres.indexes import GinIndex


class Migration(migrations.Migration):

    dependencies = [("crm", "9027_contact_messengers")]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="kinds",
            field=models.JSONField(blank=True, default=list,
                                   help_text="client/supplier/master/staff/partner — контрагент може бути кількох типів одразу",
                                   verbose_name="Типи контрагента"),
        ),
        migrations.AddField(
            model_name="contact",
            name="gender",
            field=models.CharField(blank=True, choices=[("m", "Чоловіча"), ("f", "Жіноча")], default="",
                                   help_text="Визначається автоматично за по батькові/іменем; можна виправити руками",
                                   max_length=1, verbose_name="Стать"),
        ),
        migrations.AddField(
            model_name="contact",
            name="monitor_docs",
            field=models.BooleanField(default=False,
                                      help_text="Забирати накладні/рахунки цього постачальника з пошти та месенджерів у «Вх. накладні»",
                                      verbose_name="Моніторити накладні"),
        ),
        migrations.AddField(
            model_name="contact",
            name="doc_email",
            field=models.CharField(blank=True, default="", max_length=190,
                                   help_text="Якщо накладні приходять з іншої адреси, ніж основний e-mail",
                                   verbose_name="Пошта для накладних"),
        ),
        migrations.AddIndex(
            model_name="contact",
            index=GinIndex(fields=["kinds"], name="contact_kinds_gin"),
        ),
    ]
