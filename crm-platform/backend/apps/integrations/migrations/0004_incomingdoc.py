from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0003_shop_funnel"),
        ("finance", "9020_plannedpayment_source_planned"),
    ]

    operations = [
        migrations.CreateModel(
            name="IncomingDoc",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mailbox", models.CharField(blank=True, default="", max_length=120)),
                ("sender", models.CharField(blank=True, default="", max_length=200)),
                ("subject", models.CharField(blank=True, default="", max_length=300)),
                ("message_uid", models.CharField(db_index=True, max_length=64)),
                ("received_at", models.DateTimeField(blank=True, null=True)),
                ("doc_type", models.CharField(choices=[("np_act", "Акт Нової Пошти"), ("supplier", "Накладна постачальника"), ("unknown", "Інше")], default="unknown", max_length=12)),
                ("status", models.CharField(choices=[("draft", "Чернетка"), ("confirmed", "Проведено"), ("rejected", "Відхилено")], db_index=True, default="draft", max_length=10)),
                ("parsed", models.JSONField(blank=True, default=dict)),
                ("attachments_b64", models.JSONField(blank=True, default=list)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_payable", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="finance.plannedpayment")),
            ],
            options={"ordering": ["-id"], "unique_together": {("mailbox", "message_uid")}},
        ),
    ]
