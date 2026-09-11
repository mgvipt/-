import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Якість звернення на ліді: Цільовий / Нецільовий (+ причина) / Коментар без запиту / Не відповів."""

    dependencies = [
        ("crm", "9060_payment_checkbox_return"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="quality",
            field=models.CharField(blank=True, db_index=True, default="", max_length=16,
                                   choices=[("target", "Цільовий"), ("nontarget", "Нецільовий"),
                                            ("comment", "Коментар без запиту"), ("noreply", "Не відповів")]),
        ),
        migrations.AddField(
            model_name="lead",
            name="quality_reason",
            field=models.CharField(blank=True, default="", max_length=24,
                                   help_text="Причина нецільового: spam/not_our/supplier_job/wrong/other"),
        ),
        migrations.AddField(
            model_name="lead",
            name="quality_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="lead",
            name="quality_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
