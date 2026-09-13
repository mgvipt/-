# Відгуки 13.09.2026: тексти затверджені Олегом → позначка затвердження, тестовий режим, історія текстів.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="reviewsettings",
            name="allowlist_contact_ids",
            field=models.JSONField(blank=True, default=list, help_text="Тестові контакти: у тестовому режимі просьби отримують лише вони"),
        ),
        migrations.AddField(
            model_name="reviewsettings",
            name="test_mode",
            field=models.BooleanField(default=True, help_text="Лише тестові контакти: просьби (авто і кнопка) — тільки клієнтам зі списку. Вимикає розробник"),
        ),
        migrations.AddField(
            model_name="reviewsettings",
            name="texts_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reviewsettings",
            name="texts_approved_note",
            field=models.CharField(blank=True, default="", help_text="Хто і коли затвердив тексти (або чому затвердження знято)", max_length=200),
        ),
        migrations.CreateModel(
            name="ReviewTextVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field", models.CharField(choices=[("text_main", "Основне замовлення"), ("text_test", "Тест-набір"), ("text_remind", "Нагадування")], max_length=20)),
                ("text", models.TextField(blank=True, default="")),
                ("approved", models.BooleanField(default=False)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
