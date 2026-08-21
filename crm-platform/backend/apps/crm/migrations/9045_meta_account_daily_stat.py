from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9044_meta_marketing_stats")]

    operations = [
        migrations.AddField(
            model_name="metaaddailystat",
            name="fx_rate_to_uah",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="metaaddailystat",
            name="spend_uah",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True),
        ),
        migrations.CreateModel(
            name="MetaAccountDailyStat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("ig_account_id", models.CharField(db_index=True, max_length=64)),
                ("username", models.CharField(blank=True, default="", max_length=150)),
                ("followers_total", models.PositiveBigIntegerField(blank=True, null=True)),
                ("followers_gained", models.IntegerField(blank=True, null=True)),
                ("synced_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-date", "ig_account_id"]},
        ),
        migrations.AddConstraint(
            model_name="metaaccountdailystat",
            constraint=models.UniqueConstraint(
                fields=("date", "ig_account_id"),
                name="uniq_meta_ig_account_daily",
            ),
        ),
        migrations.AddIndex(
            model_name="metaaccountdailystat",
            index=models.Index(
                fields=["ig_account_id", "date"],
                name="crm_meta_ig_account_day",
            ),
        ),
    ]
