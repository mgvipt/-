from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0011_contact_social_link"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("lead","Лід"),("deal","Сделка"),("finance","Фінанси"),("contact","Клієнт")], db_index=True, max_length=12)),
                ("object_id", models.IntegerField(db_index=True)),
                ("actor", models.CharField(blank=True, default="", max_length=80)),
                ("action", models.CharField(max_length=120)),
                ("detail", models.CharField(blank=True, default="", max_length=400)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
