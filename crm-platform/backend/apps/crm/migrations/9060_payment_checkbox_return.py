from django.db import migrations, models


class Migration(migrations.Migration):
    """ID фіскального чека ПОВЕРНЕННЯ Checkbox — щоб чек зберігався в CRM, а не тільки в кабінеті."""

    dependencies = [("crm", "9059_contact_avatar")]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="checkbox_return_id",
            field=models.CharField(blank=True, default="", max_length=64,
                                   help_text="ID чека ПОВЕРНЕННЯ Checkbox по цьому платежу"),
        ),
    ]
