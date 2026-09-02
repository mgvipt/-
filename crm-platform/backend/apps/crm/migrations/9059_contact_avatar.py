from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9058_deal_rooms")]
    operations = [
        migrations.AddField(
            model_name="contact",
            name="avatar_url",
            field=models.URLField(blank=True, default="", help_text="Тягнеться з Instagram/Facebook. Посилання тимчасове — оновлюється при новому повідомленні.", max_length=500, verbose_name="Фото профілю (з месенджера)"),
        ),
    ]
