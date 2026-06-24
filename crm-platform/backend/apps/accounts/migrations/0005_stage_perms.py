from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_org_structure")]
    operations = [
        migrations.AddField("department", "stage_view_all", models.JSONField(blank=True, default=list)),
        migrations.AddField("department", "stage_lock", models.JSONField(blank=True, default=list)),
        migrations.AddField("role", "stage_view_all", models.JSONField(blank=True, default=list)),
        migrations.AddField("role", "stage_lock", models.JSONField(blank=True, default=list)),
        migrations.AddField("user", "stage_view_all", models.JSONField(blank=True, default=list)),
        migrations.AddField("user", "stage_lock", models.JSONField(blank=True, default=list)),
    ]
