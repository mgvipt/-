from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("warehouse", "0029_internal_material_document")]
    operations = [
        migrations.AddField(model_name="internalmaterialdocument", name="content_sha256", field=models.CharField(max_length=64, blank=True, default="")),
        migrations.AddField(model_name="internalmaterialdocument", name="original_filename", field=models.CharField(max_length=255, blank=True, default="")),
    ]
