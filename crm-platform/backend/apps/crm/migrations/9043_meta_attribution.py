from django.db import migrations, models


def block_legacy_unattributed_events(apps, schema_editor):
    event = apps.get_model("crm", "MetaConversionEvent")
    event.objects.filter(status__in=("pending", "failed")).update(
        status="skipped",
        last_error="Blocked during strict Meta attribution migration: no verified ad/form ID",
    )


class Migration(migrations.Migration):
    dependencies = [("crm", "9042_meta_conversion_event")]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="meta_attribution",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Перевірена рекламна атрибуція Meta (тип джерела та стабільні ID реклами/форми)",
            ),
        ),
        migrations.AddField(
            model_name="deal",
            name="meta_attribution",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Перевірена рекламна атрибуція Meta, перенесена з ліда",
            ),
        ),
        migrations.RunPython(block_legacy_unattributed_events, migrations.RunPython.noop),
    ]
