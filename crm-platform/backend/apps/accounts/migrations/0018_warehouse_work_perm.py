from django.db import migrations

NEW = "warehouse.work"


def grant(apps, schema_editor):
    """17.09.2026: меню «Відвантаження» — окреме право. Щоб нічого не зникло, його отримують усі, у кого вже є
    «Доступ до складу» (ролі, відділи, особисті права). Кому не потрібно — забирають у картці співробітника."""
    for name in ("Role", "Department", "User"):
        model = apps.get_model("accounts", name)
        field = "extra_permissions" if name == "User" else "permissions"
        for obj in model.objects.all():
            perms = list(getattr(obj, field) or [])
            if "warehouse.view" in perms and NEW not in perms:
                setattr(obj, field, perms + [NEW])
                obj.save(update_fields=[field])


def ungrant(apps, schema_editor):
    for name in ("Role", "Department", "User"):
        model = apps.get_model("accounts", name)
        field = "extra_permissions" if name == "User" else "permissions"
        for obj in model.objects.all():
            perms = [c for c in (getattr(obj, field) or []) if c != NEW]
            setattr(obj, field, perms)
            obj.save(update_fields=[field])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_stafftransfer_chat_perms")]
    operations = [migrations.RunPython(grant, ungrant)]
