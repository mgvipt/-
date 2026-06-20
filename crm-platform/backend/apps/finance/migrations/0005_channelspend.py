from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0004_findirection")]
    operations = [
        migrations.CreateModel(
            name="ChannelSpend",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("channel", models.CharField(max_length=24)),
                ("period", models.CharField(help_text="YYYY-MM", max_length=7)),
                ("spend", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("src", models.CharField(default="manual", help_text="meta / manual", max_length=10)),
            ],
            options={"unique_together": {("channel", "period")}},
        ),
    ]
