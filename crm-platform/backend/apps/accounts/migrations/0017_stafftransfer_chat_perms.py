from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

NEW = ["conversation.staff_filter", "conversation.takeover"]


def grant(apps, schema_editor):
    """17.09.2026: вкладку «Всі співробітники» і право забирати чужий чат лишаємо керівництву
    (ролі/відділи з «Керувати ролями» або «Перевіряти чати (РОП)», роль «Руководитель отдела»).
    Відділ продажів їх НЕ отримує — менеджери більше не бачать список колег і не перехоплюють чати."""
    Role = apps.get_model("accounts", "Role")
    Department = apps.get_model("accounts", "Department")
    for model in (Role, Department):
        for obj in model.objects.all():
            perms = list(obj.permissions or [])
            lead = ("roles.manage" in perms or "conversation.supervise" in perms
                    or (model is Role and "руководит" in (obj.name or "").lower()))
            if not lead:
                continue
            add = [c for c in NEW if c not in perms]
            if add:
                obj.permissions = perms + add
                obj.save(update_fields=["permissions"])


def ungrant(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Department = apps.get_model("accounts", "Department")
    for model in (Role, Department):
        for obj in model.objects.all():
            obj.permissions = [c for c in (obj.permissions or []) if c not in NEW]
            obj.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0016_marketing_money_perm")]
    operations = [
        migrations.CreateModel(
            name="StaffTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(auto_now_add=True)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("restored_at", models.DateTimeField(blank=True, null=True)),
                ("restored", models.JSONField(blank=True, default=dict)),
                ("by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                         related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name="transfers_out", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-at"]},
        ),
        migrations.RunPython(grant, ungrant),
    ]
