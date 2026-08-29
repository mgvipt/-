from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("inbox", "0017_message_is_followup")]
    operations = [
        migrations.CreateModel(
            name="MediaLibraryItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("kind", models.CharField(choices=[("image", "Фото"), ("video", "Відео"), ("catalog", "Каталог")], default="image", max_length=16)),
                ("section", models.CharField(choices=[("colors", "Кольори"), ("quick", "Швидкі відповіді")], default="quick", max_length=16)),
                ("color_code", models.CharField(blank=True, db_index=True, max_length=48)),
                ("tags", models.CharField(blank=True, max_length=240)),
                ("public_url", models.URLField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("file", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="library_items", to="inbox.sharedlink")),
            ],
            options={"ordering": ["section", "sort", "title"]},
        ),
        migrations.CreateModel(
            name="QuickReply",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("text", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assets", models.ManyToManyField(blank=True, related_name="quick_replies", to="inbox.medialibraryitem")),
            ],
            options={"ordering": ["sort", "title"]},
        ),
    ]
