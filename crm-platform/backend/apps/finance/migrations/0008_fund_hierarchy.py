import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0007_alter_channelspend_id_alter_findirection_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="finmodelarticle",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subfunds", to="finance.finmodelarticle",
                help_text="Батьківський фонд (для підфондів)",
            ),
        ),
        migrations.AddField(
            model_name="finmodelarticle",
            name="is_envelope",
            field=models.BooleanField(
                default=False,
                help_text="Конверт: тримає гроші, отримує розподіл і робить з нього розхід",
            ),
        ),
    ]
