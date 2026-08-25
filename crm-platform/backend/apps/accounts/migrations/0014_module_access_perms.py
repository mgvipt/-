from django.db import migrations

NEW = ["lead.view", "deal.view", "inbox.view", "task.view"]


def grant(apps, schema_editor):
    """Новые права доступа к разделам выдаём ВСЕМ существующим ролям и отделам,
    чтобы после обновления никто не потерял привычные вкладки."""
    Role = apps.get_model("accounts", "Role")
    Department = apps.get_model("accounts", "Department")
    for model in (Role, Department):
        for obj in model.objects.all():
            perms = list(obj.permissions or [])
            changed = False
            for code in NEW:
                if code not in perms:
                    perms.append(code)
                    changed = True
            if changed:
                obj.permissions = perms
                obj.save(update_fields=["permissions"])


def ungrant(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Department = apps.get_model("accounts", "Department")
    for model in (Role, Department):
        for obj in model.objects.all():
            perms = [c for c in (obj.permissions or []) if c not in NEW]
            obj.permissions = perms
            obj.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_invite_username")]
    operations = [migrations.RunPython(grant, ungrant)]
