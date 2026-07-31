from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '9023_worksession_last_seen_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='findirection',
            name='parent',
            field=models.ForeignKey(blank=True, help_text='Батьківський напрямок (для піднапрямків)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='finance.findirection'),
        ),
    ]
