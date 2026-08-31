# Позначка «це РІЗНІ люди» для групи з розділу «Дублі» (31.08.2026).
# Написана руками: у проді бекенд запечений в образ, тому makemigrations всередині
# старого контейнера моделі не бачить (і тягне зайві Alter-и інших таблиць).
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("crm", "9056_deal_area"),
    ]

    operations = [
        migrations.CreateModel(
            name="DuplicateDismissal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(db_index=True, max_length=255, unique=True, verbose_name="Ключ групи")),
                ("contact_ids", models.JSONField(default=list, verbose_name="ID карток")),
                ("reason", models.CharField(blank=True, default="", max_length=200, verbose_name="Чому не дубль")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("by_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name="duplicate_dismissals", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Позначка «не дубль»",
                "verbose_name_plural": "Позначки «не дублі»",
                "ordering": ["-created_at"],
            },
        ),
    ]
