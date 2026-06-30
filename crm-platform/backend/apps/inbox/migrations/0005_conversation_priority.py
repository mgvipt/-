from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inbox", "0004_message_internal"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="priority",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="conversation",
            name="priority_reason",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="conversation",
            name="priority_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conversation",
            name="priority_seen_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
