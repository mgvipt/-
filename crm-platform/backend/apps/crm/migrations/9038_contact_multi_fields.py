from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9037_contact_payment_purpose")]
    operations = [
        migrations.AddField(model_name="contact", name="emails_extra",
            field=models.JSONField(blank=True, default=list,
                help_text="[{label,value}] — кілька пошт з власними назвами полів", verbose_name="Додаткові email")),
        migrations.AddField(model_name="contact", name="phones_extra",
            field=models.JSONField(blank=True, default=list,
                help_text="[{label,value}] — кілька телефонів з назвами", verbose_name="Додаткові телефони")),
        migrations.AddField(model_name="contact", name="accounts",
            field=models.JSONField(blank=True, default=list,
                help_text="[{label,iban,active}] — активний рахунок = на який оплачуємо через ФОП", verbose_name="Рахунки (постачальник)")),
        migrations.AddField(model_name="contact", name="monitor_emails",
            field=models.JSONField(blank=True, default=list,
                help_text="[email] — додаткові адреси, з яких приходять накладні цього постачальника", verbose_name="Пошти для моніторингу")),
    ]
