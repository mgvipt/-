from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("crm", "0012_activitylog")]
    operations = [
        migrations.CreateModel(
            name="AutomationRule",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trigger", models.CharField(choices=[("manager_reply","Менеджер/AI відповів"),("client_reply","Клієнт відповів"),("ready_buy","Готовність купити"),("payment","Оплата отримана")], max_length=20)),
                ("enabled", models.BooleanField(default=True)),
                ("from_stage", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="crm.stage")),
                ("funnel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="automation_rules", to="crm.funnel")),
                ("to_stage", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="crm.stage")),
            ],
            options={"unique_together": {("funnel", "from_stage", "trigger")}},
        ),
    ]
