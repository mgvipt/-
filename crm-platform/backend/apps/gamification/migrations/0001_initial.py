from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="ManagerLevel", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
            ("total_xp", models.IntegerField(default=0)),
            ("level", models.IntegerField(default=1)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("manager", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="gam_level", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="BadgeAward", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
            ("badge_code", models.CharField(max_length=32)),
            ("awarded_at", models.DateTimeField(auto_now_add=True)),
            ("meta", models.JSONField(blank=True, default=dict)),
            ("manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gam_badges", to=settings.AUTH_USER_MODEL)),
        ], options={"unique_together": {("manager", "badge_code")}}),
        migrations.CreateModel(name="XPEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
            ("kind", models.CharField(max_length=32)),
            ("xp", models.IntegerField(default=0)),
            ("ref_type", models.CharField(blank=True, default="", max_length=24)),
            ("ref_id", models.CharField(blank=True, default="", max_length=40)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("meta", models.JSONField(blank=True, default=dict)),
            ("manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="xp_events", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddConstraint(model_name="xpevent", constraint=models.UniqueConstraint(
            condition=models.Q(("ref_id", ""), _negated=True), fields=("kind", "ref_type", "ref_id"), name="uniq_xp_ref")),
        migrations.AddIndex(model_name="xpevent", index=models.Index(fields=["manager", "created_at"], name="gam_xp_mgr_idx")),
    ]
