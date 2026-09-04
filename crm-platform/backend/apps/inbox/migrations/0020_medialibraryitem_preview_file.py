from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("inbox", "0019_media_library_material")]

    operations = [
        migrations.AddField(
            model_name="medialibraryitem",
            name="preview_file",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="library_preview_items", to="inbox.sharedlink"),
        ),
    ]
