import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0013_transfer"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="WorkDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("status", models.CharField(default="worked", max_length=12)),
                ("note", models.CharField(blank=True, default="", max_length=160)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workdays", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date"], "unique_together": {("user", "date")}},
        ),
    ]
