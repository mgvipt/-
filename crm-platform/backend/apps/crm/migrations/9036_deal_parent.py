from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [('crm', '9035_task_module_v1')]

    operations = [
        migrations.AddField(
            model_name='deal',
            name='parent_deal',
            field=models.ForeignKey(blank=True, help_text='Батьківська сделка (дозамовлення — їде однією посилкою)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='crm.deal'),
        ),
    ]
