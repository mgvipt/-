from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("telephony", "0001_initial")]
    operations = [
        migrations.AddField(model_name="call", name="recording_file",
            field=models.CharField(blank=True, max_length=255, help_text="імʼя файлу запису на FreePBX")),
        migrations.AddField(model_name="call", name="extension",
            field=models.CharField(blank=True, max_length=16, help_text="внутрішній номер менеджера")),
        migrations.AddField(model_name="call", name="disposition",
            field=models.CharField(blank=True, max_length=24, help_text="ANSWERED / NO ANSWER / BUSY / FAILED")),
        migrations.AddField(model_name="call", name="started_at",
            field=models.DateTimeField(blank=True, null=True)),
    ]
