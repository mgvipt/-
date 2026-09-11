import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Знімок платежів дня («Закрити день») — замість скріна журналу в Telegram о 18:00."""

    dependencies = [
        ("finance", "9026_plannedpayment_paid_from_advance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DaySnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("version", models.PositiveSmallIntegerField(default=1)),
                ("kind", models.CharField(choices=[("manual", "Вручну"), ("auto", "Авто 18:00"), ("reclose", "Перезнімок")],
                                          default="manual", max_length=10)),
                ("closed_at", models.DateTimeField(auto_now_add=True)),
                ("rows", models.JSONField(blank=True, default=list)),
                ("totals", models.JSONField(blank=True, default=dict)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("reopened_at", models.DateTimeField(blank=True, null=True)),
                ("closed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                related_name="+", to=settings.AUTH_USER_MODEL)),
                ("reopened_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "-version"], "unique_together": {("date", "version")}},
        ),
    ]
