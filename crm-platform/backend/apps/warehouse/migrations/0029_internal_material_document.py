from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0028_reorder")]
    operations = [migrations.CreateModel(
        name="InternalMaterialDocument",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title_uk", models.CharField(max_length=240)),
            ("title_ru", models.CharField(blank=True, default="", max_length=240)),
            ("kind", models.CharField(choices=[("certificate", "Сертифікат"), ("protocol", "Протокол"), ("technical", "Технічний лист"), ("safety", "Паспорт безпеки"), ("other", "Інший документ")], default="protocol", max_length=24)),
            ("source_url", models.URLField(max_length=500)),
            ("source_key", models.CharField(editable=False, max_length=240, unique=True)),
            ("document_number", models.CharField(blank=True, default="", max_length=120)),
            ("original_language", models.CharField(blank=True, default="", max_length=16)),
            ("issued_at", models.DateField(blank=True, null=True)),
            ("valid_until", models.DateField(blank=True, null=True)),
            ("is_archived", models.BooleanField(default=False)),
            ("is_active", models.BooleanField(default=True)),
            ("notes_internal", models.TextField(blank=True, default="")),
            ("notes_ru", models.TextField(blank=True, default="")),
            ("team_access_verified", models.BooleanField(default=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("products", models.ManyToManyField(blank=True, related_name="internal_documents", to="warehouse.product")),
        ], options={"ordering": ["is_archived", "title_uk", "id"]},
    )]
