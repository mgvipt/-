from django.db import migrations

NEW = ["marketing.money"]


def grant(apps, schema_editor):
    """Выдаём тем, у кого уже есть доступ к маркетингу, чтобы не потерять цифры."""
    Role = apps.get_model("accounts", "Role")
    Department = apps.get_model("accounts", "Department")
    for model in (Role, Department):
        for obj in model.objects.all():
            perms = list(obj.permissions or [])
            if "marketing.view" in perms and "marketing.money" not in perms:
                perms.append("marketing.money")
                obj.permissions = perms
                obj.save(update_fields=["permissions"])


def ungrant(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Department = apps.get_model("accounts", "Department")
    for model in (Role, Department):
        for obj in model.objects.all():
            obj.permissions = [c for c in (obj.permissions or []) if c not in NEW]
            obj.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_contact_view_perm")]
    operations = [migrations.RunPython(grant, ungrant)]
