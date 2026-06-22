import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0011_tx_currency_advisory")]
    operations = [
        migrations.CreateModel(
            name="TransactionAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(default="application/octet-stream", max_length=120)),
                ("size", models.PositiveIntegerField(default=0)),
                ("data", models.BinaryField()),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="finance.transaction")),
            ],
            options={"ordering": ["-uploaded_at"]},
        ),
    ]
