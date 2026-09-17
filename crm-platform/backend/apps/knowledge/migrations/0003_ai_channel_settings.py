from django.db import migrations, models


class Migration(migrations.Migration):
    """17.09.2026: налаштування ІІ у каналах — пауза після менеджера і ліміт відповідей на добу (AI ЦЕНТР)."""

    dependencies = [("knowledge", "0002_knowledgesettings_webchat_ai_enabled_and_more")]

    operations = [
        migrations.AddField(
            model_name="knowledgesettings",
            name="ai_silence_hours",
            field=models.PositiveSmallIntegerField(default=12,
                help_text="Скільки годин ІІ мовчить у чаті після повідомлення менеджера"),
        ),
        migrations.AddField(
            model_name="knowledgesettings",
            name="ai_max_per_day",
            field=models.PositiveSmallIntegerField(default=15,
                help_text="Скільки відповідей ІІ може дати в одному чаті за добу"),
        ),
    ]
