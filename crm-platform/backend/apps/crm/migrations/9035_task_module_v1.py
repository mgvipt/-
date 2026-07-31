from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '9034_zamerproject_deleted_at'),
        ('inbox', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='priority',
            field=models.CharField(
                choices=[('low', 'Низький'), ('normal', 'Звичайний'), ('high', 'Високий')],
                db_index=True, default='normal', max_length=8),
        ),
        migrations.AddField(
            model_name='task',
            name='contact',
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tasks', to='crm.contact'),
        ),
        migrations.AddField(
            model_name='task',
            name='conversation',
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tasks', to='inbox.conversation'),
        ),
        migrations.AddField(
            model_name='task',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tasks_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='task',
            name='due_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
