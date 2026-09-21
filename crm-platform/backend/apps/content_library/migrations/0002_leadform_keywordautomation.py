from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_microcement(apps, schema_editor):
    Instruction = apps.get_model('content_library', 'Instruction')
    LeadForm = apps.get_model('content_library', 'LeadForm')
    KeywordAutomation = apps.get_model('content_library', 'KeywordAutomation')
    instruction = Instruction.objects.filter(slug='microcement').first()
    if not instruction:
        return
    form, _ = LeadForm.objects.update_or_create(
        slug='microcement',
        defaults={
            'name': 'Microcement — повна техкарта',
            'title': 'Отримайте повну техкарту Microcement',
            'intro': 'Залиште ім’я, контакт та оберіть зручний канал зв’язку. Інструкція відкриється одразу.',
            'instruction': instruction,
            'fields': ['name', 'phone', 'email'],
            'channels': ['viber', 'whatsapp', 'email', 'telegram'],
            'consent_text': 'Хочу отримувати нові інструкції та пропозиції Wallcov',
            'submit_text': 'Відкрити повну інструкцію',
            'enabled': True,
        },
    )
    KeywordAutomation.objects.update_or_create(
        title='Instagram · МІКРО (коментарі + Direct)',
        defaults={
            'keywords': ['МІКРО'],
            'match_mode': 'exact',
            'platforms': ['instagram'],
            'form': form,
            'reply_text': ('Зібрали повну технологічну карту Microcement Wallcov 👇\n\n'
                           'Оберіть зручний канал — Viber, WhatsApp, Telegram або email:\n'
                           '{form_url}\n\nІнструкція відкриється одразу після контакту.'),
            'public_replies': [
                'Готово — надіслали техкарту в Direct 👇',
                'Інструкція вже летить у Direct ✅',
                'Надіслали повну техкарту в Direct 👌',
            ],
            'direct_enabled': True,
            'comment_enabled': True,
            'enabled': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('content_library', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeadForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(unique=True)),
                ('name', models.CharField(max_length=160)),
                ('title', models.CharField(max_length=240)),
                ('intro', models.TextField(blank=True)),
                ('fields', models.JSONField(blank=True, default=list)),
                ('channels', models.JSONField(blank=True, default=list)),
                ('consent_text', models.CharField(blank=True, max_length=300)),
                ('submit_text', models.CharField(default='Відкрити повну інструкцію', max_length=120)),
                ('enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('instruction', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lead_forms', to='content_library.instruction')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name', 'id']},
        ),
        migrations.CreateModel(
            name='KeywordAutomation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=180)),
                ('keywords', models.JSONField(default=list)),
                ('match_mode', models.CharField(choices=[('exact', 'Точний збіг'), ('contains', 'Містить фразу')], default='exact', max_length=16)),
                ('platforms', models.JSONField(default=list)),
                ('reply_text', models.TextField()),
                ('public_replies', models.JSONField(blank=True, default=list)),
                ('direct_enabled', models.BooleanField(default=True)),
                ('comment_enabled', models.BooleanField(default=True)),
                ('chatplace_bot_id', models.CharField(blank=True, max_length=64)),
                ('chatplace_automation_id', models.CharField(blank=True, max_length=64)),
                ('chatplace_status', models.CharField(blank=True, max_length=24)),
                ('chatplace_error', models.CharField(blank=True, max_length=500)),
                ('synced_at', models.DateTimeField(blank=True, null=True)),
                ('enabled', models.BooleanField(default=False)),
                ('last_triggered_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='automations', to='content_library.leadform')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['title', 'id']},
        ),
        migrations.CreateModel(
            name='KeywordAutomationRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyword', models.CharField(max_length=120)),
                ('status', models.CharField(choices=[('processing', 'Обробка'), ('captured', 'Зафіксовано'), ('sent', 'Надіслано'), ('duplicate', 'Повтор'), ('failed', 'Помилка')], default='processing', max_length=16)),
                ('error', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('automation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='content_library.keywordautomation')),
                ('message', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='keyword_automation_run', to='inbox.message')),
                ('profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='keyword_runs', to='content_library.audienceprofile')),
                ('reply_message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='inbox.message')),
            ],
        ),
        migrations.RunPython(seed_microcement, migrations.RunPython.noop),
    ]
