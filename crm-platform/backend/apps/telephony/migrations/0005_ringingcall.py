from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("telephony", "0004_call_line"), ("crm", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="RingingCall",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uniqueid", models.CharField(max_length=64, unique=True)),
                ("number", models.CharField(max_length=32)),
                ("line", models.CharField(blank=True, max_length=60)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("contact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="crm.contact")),
            ],
        ),
    ]
