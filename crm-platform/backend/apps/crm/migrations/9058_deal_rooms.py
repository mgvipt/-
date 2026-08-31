from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("crm", "9057_duplicate_dismissal")]
    operations = [
        migrations.CreateModel(
            name="DealRoom",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, verbose_name="Приміщення")),
                ("area_m2", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Площа, м²")),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("deal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rooms", to="crm.deal")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.AddField(
            model_name="dealitem",
            name="room",
            field=models.ForeignKey(blank=True, help_text="Приміщення (порожньо = загальна позиція)", null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name="items", to="crm.dealroom"),
        ),
    ]
