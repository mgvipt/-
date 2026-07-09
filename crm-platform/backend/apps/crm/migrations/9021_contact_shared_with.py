from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('crm', '9020_dealitem_cost_alter_payment_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='shared_with',
            field=models.ManyToManyField(
                blank=True,
                help_text='Доступ к клиенту выдан этим менеджерам (шаринг). Свои клиенты видны и без этого.',
                related_name='contacts_shared',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
