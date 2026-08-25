from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_user_idle_timeout_min")]
    operations = [
        migrations.AddField(
            model_name="invite",
            name="username",
            field=models.CharField(blank=True, default="", help_text="Бажаний логін; якщо порожньо — з пошти", max_length=150),
        ),
    ]
