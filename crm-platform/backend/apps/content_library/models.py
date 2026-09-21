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
