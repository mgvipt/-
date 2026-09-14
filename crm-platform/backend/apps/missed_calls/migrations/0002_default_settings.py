# Створено через `makemigrations missed_calls --empty --name default_settings` (14.09.2026).
# Один рядок налаштувань створюється під час міграції: тоді GET-запити (віджет телефона, смоук)
# ніколи нічого не пишуть у БД. active_since = момент міграції → черга рахує лише НОВІ пропущені.

from django.db import migrations


def create_settings(apps, schema_editor):
    from django.utils import timezone
    Settings = apps.get_model("missed_calls", "MissedCallSettings")
    if not Settings.objects.exists():
        Settings.objects.create(active_since=timezone.now(), work_days=[0, 1, 2, 3, 4, 5, 6])


class Migration(migrations.Migration):

    dependencies = [
        ('missed_calls', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_settings, migrations.RunPython.noop),
    ]
