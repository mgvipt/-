import secrets
import uuid
from django.conf import settings
from django.db import models


def token():
    return secrets.token_urlsafe(32)


class Instruction(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    article_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=16, default='draft', choices=[('draft','Чернетка'),('published','Опубліковано')])
    version = models.PositiveIntegerField(default=1)
    content = models.JSONField(default=dict)
    products = models.ManyToManyField('warehouse.Product', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def public_url(self):
        return 'https://wallcov.com.ua/instructions/' + self.slug


class AudienceProfile(models.Model):
    contact = models.OneToOneField('crm.Contact', on_delete=models.CASCADE, related_name='content_audience')
    first_touch_at = models.DateTimeField(auto_now_add=True)
    last_touch_at = models.DateTimeField(auto_now=True)
    first_touch = models.JSONField(default=dict)
    last_touch = models.JSONField(default=dict)
    preferred_channel = models.CharField(max_length=24, blank=True)
    marketing_consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, default='new')
    tags = models.JSONField(default=list)
    unsubscribe_token = models.CharField(max_length=64, unique=True, default=token)


class AudienceIdentity(models.Model):
    profile = models.ForeignKey(AudienceProfile, on_delete=models.CASCADE, related_name='identities')
    kind = models.CharField(max_length=16)
    value = models.CharField(max_length=254)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind','value'], name='unique_content_identity')]


class ConsentEvent(models.Model):
    profile = models.ForeignKey(AudienceProfile, on_delete=models.CASCADE)
    granted = models.BooleanField()
    text_version = models.CharField(max_length=40, default='wallcov-materials-20260921')
    source = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)


class GuideRequest(models.Model):
    submission_id = models.CharField(max_length=80, unique=True)
    payload_hash = models.CharField(max_length=64)
    instruction = models.ForeignKey(Instruction, on_delete=models.PROTECT)
    profile = models.ForeignKey(AudienceProfile, on_delete=models.PROTECT, related_name='requests')
    token = models.CharField(max_length=64, unique=True, default=token)
    context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class InstructionShare(models.Model):
    token = models.CharField(max_length=64, unique=True, default=token)
    instruction = models.ForeignKey(Instruction, on_delete=models.PROTECT)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    conversation = models.ForeignKey('inbox.Conversation', on_delete=models.PROTECT)
    contact = models.ForeignKey('crm.Contact', on_delete=models.SET_NULL, null=True)
    message = models.OneToOneField('inbox.Message', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class InstructionEvent(models.Model):
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    instruction = models.ForeignKey(Instruction, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    profile = models.ForeignKey(AudienceProfile, on_delete=models.SET_NULL, null=True, blank=True)
    share = models.ForeignKey(InstructionShare, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=40, db_index=True)
    context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class LeadForm(models.Model):
    """Редагована форма видачі інструкції. CRM є джерелом конфігурації для сайту."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=160)
    title = models.CharField(max_length=240)
    intro = models.TextField(blank=True)
    instruction = models.ForeignKey(Instruction, on_delete=models.PROTECT, related_name='lead_forms')
    fields = models.JSONField(default=list, blank=True)
    channels = models.JSONField(default=list, blank=True)
    consent_text = models.CharField(max_length=300, blank=True)
    submit_text = models.CharField(max_length=120, default='Відкрити повну інструкцію')
    enabled = models.BooleanField(default=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self):
        return self.name


class KeywordAutomation(models.Model):
    MATCH = [('exact', 'Точний збіг'), ('contains', 'Містить фразу')]
    title = models.CharField(max_length=180)
    keywords = models.JSONField(default=list)
    match_mode = models.CharField(max_length=16, choices=MATCH, default='exact')
    platforms = models.JSONField(default=list)
    form = models.ForeignKey(LeadForm, on_delete=models.PROTECT, related_name='automations')
    reply_text = models.TextField()
    public_replies = models.JSONField(default=list, blank=True)
    direct_enabled = models.BooleanField(default=True)
    comment_enabled = models.BooleanField(default=True)
    chatplace_bot_id = models.CharField(max_length=64, blank=True)
    chatplace_automation_id = models.CharField(max_length=64, blank=True)
    chatplace_status = models.CharField(max_length=24, blank=True)
    chatplace_error = models.CharField(max_length=500, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title', 'id']

    def __str__(self):
        return self.title


class KeywordAutomationRun(models.Model):
    STATUS = [('processing', 'Обробка'), ('captured', 'Зафіксовано'), ('sent', 'Надіслано'),
              ('duplicate', 'Повтор'), ('failed', 'Помилка')]
    message = models.OneToOneField('inbox.Message', on_delete=models.CASCADE,
                                   related_name='keyword_automation_run')
    automation = models.ForeignKey(KeywordAutomation, on_delete=models.PROTECT, related_name='runs')
    profile = models.ForeignKey(AudienceProfile, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name='keyword_runs')
    reply_message = models.ForeignKey('inbox.Message', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='+')
    keyword = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=STATUS, default='processing')
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
