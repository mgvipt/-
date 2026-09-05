from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("inbox", "0020_medialibraryitem_preview_file"), ("crm", "9060_payment_checkbox_return")]
    operations = [migrations.CreateModel(name="LandingSubmission", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("request_id", models.CharField(max_length=80, unique=True)),
        ("payload_hash", models.CharField(max_length=64)),
        ("phone_hash", models.CharField(max_length=64)),
        ("photos", models.JSONField(default=list)),
        ("accepted_at", models.DateTimeField(blank=True, null=True)),
        ("responded_at", models.DateTimeField(blank=True, null=True)),
        ("escalated_at", models.DateTimeField(blank=True, null=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inbox.conversation")),
        ("deal", models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="landing_receipt", to="crm.deal")),
        ("task", models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="landing_receipt", to="crm.task")),
    ])]
