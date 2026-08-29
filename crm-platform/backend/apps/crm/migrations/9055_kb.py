from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("crm", "9054_ga4_channels")]
    operations = [
        migrations.CreateModel(
            name="KbEntry",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ext_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("question", models.TextField()),
                ("answer", models.TextField(blank=True, default="")),
                ("specific_rules", models.TextField(blank=True, default="")),
                ("source", models.CharField(choices=[("chatplace", "ChatPlace-імпорт"), ("manual", "Додано вручну"), ("dialog", "З діалогу")], default="manual", max_length=16)),
                ("client_chat_count", models.IntegerField(default=0, help_text="Скільки разів клієнти про це питали (популярність)")),
                ("tags", models.CharField(blank=True, default="", max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-client_chat_count", "question"]},
        ),
        migrations.CreateModel(
            name="KbUnknownQuestion",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ext_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("question", models.TextField()),
                ("status", models.CharField(choices=[("new", "Нове"), ("answered", "Додано в базу"), ("ignored", "Ігнор")], db_index=True, default="new", max_length=16)),
                ("source", models.CharField(choices=[("chatplace", "ChatPlace"), ("dialog", "З діалогу CRM")], default="chatplace", max_length=16)),
                ("times_asked", models.IntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("answer_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="from_questions", to="crm.kbentry")),
            ],
            options={"ordering": ["-times_asked", "-created_at"]},
        ),
    ]
