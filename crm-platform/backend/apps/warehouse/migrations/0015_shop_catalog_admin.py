import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0014_product_is_drop")]

    operations = [
        migrations.AddField(model_name="productimage", name="alt_text", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="productimage", name="is_approved", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="productimage", name="is_primary", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="productimage", name="variant_key", field=models.CharField(blank=True, default="", max_length=40)),
        migrations.AddField(model_name="product", name="seo_categories", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="product", name="seo_description", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="product", name="seo_faqs", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="product", name="seo_h1", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="product", name="seo_index", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="product", name="seo_title", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="product", name="shop_badges", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="product", name="shop_beginner", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="product", name="shop_benefits", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="product", name="shop_contents", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="product", name="shop_effect", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField(model_name="product", name="shop_enabled", field=models.BooleanField(default=False, verbose_name="Показувати на сайті")),
        migrations.AddField(model_name="product", name="shop_full_description", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="product", name="shop_group_key", field=models.CharField(blank=True, db_index=True, default="", max_length=96)),
        migrations.AddField(model_name="product", name="shop_has_board", field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name="product", name="shop_instruction_url", field=models.URLField(blank=True, default="", max_length=500)),
        migrations.AddField(model_name="product", name="shop_is_tinted", field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name="product", name="shop_last_sync_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="product", name="shop_managed", field=models.BooleanField(db_index=True, default=False)),
        migrations.AddField(model_name="product", name="shop_parent_name", field=models.CharField(blank=True, default="", max_length=255, verbose_name="Назва покриття на сайті")),
        migrations.AddField(model_name="product", name="shop_remote_url", field=models.URLField(blank=True, default="", max_length=500)),
        migrations.AddField(model_name="product", name="shop_rooms", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="product", name="shop_short_description", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="product", name="shop_slug", field=models.SlugField(blank=True, default="", max_length=160)),
        migrations.AddField(model_name="product", name="shop_sort", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="product", name="shop_status", field=models.CharField(choices=[("draft", "Чернетка"), ("ready", "Готовий"), ("published", "Опублікований"), ("hidden", "Прихований"), ("error", "Помилка")], db_index=True, default="draft", max_length=16)),
        migrations.AddField(model_name="product", name="shop_sync_error", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="product", name="shop_variant_name", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="product", name="shop_variant_order", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="product", name="shop_variant_type", field=models.CharField(blank=True, default="sample", max_length=32)),
        migrations.AddField(model_name="product", name="shop_video_url", field=models.URLField(blank=True, default="", max_length=500)),
        migrations.CreateModel(
            name="ShopSyncEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("action", models.CharField(default="upsert", max_length=16)),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("pending", "Очікує"), ("processing", "Передається"), ("processed", "Готово"), ("failed", "Помилка"), ("superseded", "Замінено новішою подією")], db_index=True, default="pending", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shop_sync_events", to="warehouse.product")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
