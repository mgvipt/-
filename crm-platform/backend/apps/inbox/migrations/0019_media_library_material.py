from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inbox", "0018_color_media_library")]

    operations = [
        migrations.AddField(
            model_name="medialibraryitem",
            name="material",
            field=models.CharField(db_index=True, default="Мокрий шовк", max_length=100),
        ),
    ]
