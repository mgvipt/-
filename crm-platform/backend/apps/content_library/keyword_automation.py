"""Фіксація кодових слів у CRM. Відповіді виконує синхронізована автоматизація ChatPlace."""
import re
import unicodedata
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from .models import (AudienceIdentity, AudienceProfile, InstructionEvent,
                     KeywordAutomation, KeywordAutomationRun)


def _normal(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = re.sub(r'\s+', ' ', value).strip()
    return value.strip(' .,!?:;«»"\'()[]{}')


def _match(rule, text):
    incoming = _normal(text)
    for raw in rule.keywords or []:
        keyword = _normal(raw)
        if keyword and ((rule.match_mode == 'contains' and keyword in incoming) or incoming == keyword):
            return str(raw).strip()
    return ''


def _platform(conversation):
    kind = str(conversation.channel.kind or '').lower()
    if kind == 'instagram' or 'instagram' in str(conversation.channel.name or '').lower():
        return 'instagram'
    return kind


def _context(conversation, rule, keyword):
    card = (conversation.config or {}).get('source_card') or {}
    is_comment = str(conversation.external_chat_id or '').startswith('comment:')
    instruction = rule.form.instruction
    return {
        'source_platform': _platform(conversation),
        'source_content_id': str(card.get('media_id') or ''),
        'source_url': str(card.get('permalink') or ''),
        'utm_source': _platform(conversation),
        'utm_medium': 'comment' if is_comment else 'direct',
        'utm_campaign': rule.form.slug + '_guide',
        'utm_content': 'keyword_' + _normal(keyword),
        'keyword': keyword,
        'conversation_id': conversation.id,
        'document_url': instruction.public_url,
        'article_url': instruction.article_url,
    }


def process_keyword_message(message):
    """Знайти правило та додати контакт до аудиторії.

    Публічну відповідь під коментарем і повідомлення в Direct надсилає ChatPlace.
    CRM лише фіксує контакт та джерело, щоб не створювати дубль відповіді.
    """
    if not message or message.direction != 'in' or message.internal or not (message.text or '').strip():
        return None
    conversation = message.conversation
    platform = _platform(conversation)
    rules = (KeywordAutomation.objects.filter(enabled=True, form__enabled=True,
                                               form__instruction__status='published')
             .select_related('form__instruction').order_by('id'))
    rule = keyword = None
    for candidate in rules:
        if platform not in (candidate.platforms or []):
            continue
        matched = _match(candidate, message.text)
        if matched:
            rule, keyword = candidate, matched
            break
    if not rule:
        return None

    with transaction.atomic():
        run, created = KeywordAutomationRun.objects.select_for_update().get_or_create(
            message=message, defaults={'automation': rule, 'keyword': keyword})
        if not created:
            return run

    try:
        contact = conversation.contact
        if contact is None:
            raise ValueError('У діалозі немає картки клієнта')
        context = _context(conversation, rule, keyword)
        profile, new_profile = AudienceProfile.objects.get_or_create(
            contact=contact,
            defaults={'first_touch': context, 'last_touch': context,
                      'preferred_channel': 'instagram', 'tags': [rule.form.slug + '_keyword']},
        )
        tags = set(profile.tags or [])
        tags.add(rule.form.slug + '_keyword')
        profile.tags = sorted(tags)
        profile.last_touch = context
        if not profile.preferred_channel:
            profile.preferred_channel = 'instagram'
        profile.save()
        identity = (str(contact.social_link or '').strip() or str(contact.nickname or '').strip()
                    or ('instagram:' + str(conversation.external_chat_id)))
        AudienceIdentity.objects.get_or_create(kind='instagram', value=identity,
                                               defaults={'profile': profile})
        run.profile = profile
        recent = (KeywordAutomationRun.objects.filter(automation=rule, profile=profile, status='captured',
                                                       created_at__gte=timezone.now()-timedelta(minutes=5))
                  .exclude(pk=run.pk).exists())
        if recent:
            run.status = 'duplicate'
            run.save(update_fields=['profile', 'status', 'updated_at'])
            return run
        run.status = 'captured'
        run.save(update_fields=['profile', 'status', 'updated_at'])
        rule.last_triggered_at = timezone.now()
        rule.save(update_fields=['last_triggered_at'])
        InstructionEvent.objects.create(
            instruction=rule.form.instruction, version=rule.form.instruction.version,
            profile=profile, name='keyword_triggered', context=context)
        return run
    except Exception as exc:
        run.status = 'failed'
        run.error = str(exc)[:500]
        run.save(update_fields=['profile', 'status', 'error', 'updated_at'])
        return run
