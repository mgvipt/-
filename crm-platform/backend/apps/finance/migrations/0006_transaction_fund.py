from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("finance", "0005_channelspend")]
    operations = [
        migrations.AddField(
            model_name="transaction",
            name="fin_article",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="finance.finmodelarticle", help_text="Фонд (стаття финмоделі)"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="channel",
            field=models.CharField(blank=True, default="", help_text="Канал/джерело надходження", max_length=24),
        ),
    ]
