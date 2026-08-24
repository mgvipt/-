from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9046_weekly_manager_review"),
    ]

    operations = [
        migrations.CreateModel(
            name="KpLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=24, unique=True)),
                ("html", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("deal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kp_links", to="crm.deal")),
            ],
            options={"ordering": ["-id"]},
        ),
    ]
