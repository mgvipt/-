from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_extension"),
        ("crm", "0001_initial"),
    ]
    operations = [
        # ── Department: дерево + права відділу + координати карти ──
        migrations.AddField("department", "parent", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name="children", to="accounts.department")),
        migrations.AddField("department", "permissions", models.JSONField(default=list, blank=True)),
        migrations.AddField("department", "open_lines", models.JSONField(default=list, blank=True)),
        migrations.AddField("department", "color", models.CharField(max_length=9, blank=True)),
        migrations.AddField("department", "pos_x", models.FloatField(default=0)),
        migrations.AddField("department", "pos_y", models.FloatField(default=0)),
        migrations.AddField("department", "sort", models.IntegerField(default=0)),
        migrations.AddField("department", "funnels", models.ManyToManyField(
            blank=True, related_name="departments", to="crm.funnel")),
        migrations.AlterModelOptions("department", options={"ordering": ["sort", "name"]}),
        # ── User: індивідуальні права ──
        migrations.AddField("user", "extra_permissions", models.JSONField(default=list, blank=True)),
        migrations.AddField("user", "denied_permissions", models.JSONField(default=list, blank=True)),
        migrations.AddField("user", "extra_open_lines", models.JSONField(default=list, blank=True)),
        migrations.AddField("user", "extra_funnels", models.ManyToManyField(
            blank=True, related_name="extra_users", to="crm.funnel")),
        # ── Invite ──
        migrations.CreateModel(
            name="Invite",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("first_name", models.CharField(blank=True, max_length=150)),
                ("last_name", models.CharField(blank=True, max_length=150)),
                ("token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("status", models.CharField(choices=[("pending", "Очікує"), ("accepted", "Прийнято"), ("revoked", "Відкликано"), ("expired", "Прострочено")], default="pending", max_length=12)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sent_invites", to=settings.AUTH_USER_MODEL)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invites", to="accounts.department")),
                ("role", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounts.role")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
