import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_user_account_kind"),
        ("crm", "9032_contact_portal_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="ZamerStageReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("stage_id", models.CharField(max_length=80)),
                ("title", models.CharField(max_length=255)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Очікує перевірки"),
                        ("accepted", "Прийнято"),
                        ("rework", "Потрібно виправити"),
                    ],
                    db_index=True, default="pending", max_length=16,
                )),
                ("note", models.TextField(blank=True, default="")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("contact", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="zamer_stage_reviews", to="crm.contact",
                )),
                ("project", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="stage_reviews", to="crm.zamerproject",
                )),
                ("requested_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="requested_zamer_stage_reviews",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("reviewed_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="reviewed_zamer_stages", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="zamerstagereview",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("project", "stage_id"),
                name="uniq_pending_project_stage_review",
            ),
        ),
        migrations.AddIndex(
            model_name="zamerstagereview",
            index=models.Index(fields=["status", "created_at"], name="zamer_review_queue_idx"),
        ),
    ]
