from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "9033_zamer_stage_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="zamerproject",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
