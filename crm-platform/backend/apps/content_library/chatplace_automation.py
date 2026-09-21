"""Синхронізація CRM-правил кодових слів з ChatPlace."""
from urllib.parse import urlencode

from django.utils import timezone

from apps.inbox.chatplace import _mcp


INSTAGRAM_BOT_ID = '647e28e9-73fd-4f06-81cc-5970409a7381'


def _automation_id(value):
    if isinstance(value, str):
        return value if len(value) >= 30 else ''
    if not isinstance(value, dict):
        return ''
    for key in ('automationId', 'automation_id', 'id'):
        if value.get(key):
            return str(value[key])
    for key in ('automation', 'data', 'result'):
        found = _automation_id(value.get(key))
        if found:
            return found
    return ''


def form_url(rule):
    query = urlencode({
        'utm_source': 'instagram',
        'utm_medium': 'automation',
        'utm_campaign': rule.form.slug + '_guide',
        'utm_content': 'keyword_' + str((rule.keywords or ['guide'])[0]).strip().casefold(),
    })
    return 'https://wallcov.com.ua/get/%s?%s' % (rule.form.slug, query)


def sync_to_chatplace(rule):
    """Створити нову версію сценарію та безпечно замінити попередню."""
    triggers = []
    suffix = 'Equals' if rule.match_mode == 'exact' else 'Contains'
    if rule.direct_enabled:
        triggers.append('message' + suffix)
    if rule.comment_enabled:
        triggers.append('comment' + suffix)
    keywords = [str(x).strip() for x in (rule.keywords or []) if str(x).strip()]
    if not triggers:
        raise ValueError('Увімкніть Direct або коментарі')
    if not keywords:
        raise ValueError('Додайте хоча б одне кодове слово')
    if rule.comment_enabled and not (rule.public_replies or []):
        raise ValueError('Додайте хоча б одну публічну відповідь на коментар')

    link = form_url(rule)
    direct_text = (rule.reply_text or '').replace('{form_url}', link).replace(
        '{instruction_title}', rule.form.instruction.title).strip()
    if not direct_text:
        raise ValueError('Додайте текст повідомлення в Direct')
    args = {
        'botId': INSTAGRAM_BOT_ID,
        'triggerType': triggers,
        'startMessages': keywords,
        'templateType': 'base',
        'welcomeMessage': direct_text,
        'welcomeButton': 'Отримати інструкцію',
        'messageWithLink': 'Заповніть коротку форму — інструкція відкриється одразу.',
        'buttonText': 'Відкрити форму',
        'buttonLink': link,
    }
    if rule.comment_enabled:
        args['autoAnswers'] = [str(x).strip() for x in rule.public_replies if str(x).strip()]

    previous_id = rule.chatplace_automation_id
    created = _mcp('automations_quick_setup', args)
    new_id = _automation_id(created)
    if not new_id:
        # Quick Setup іноді повертає лише текстове підтвердження. Нові ID ChatPlace
        # є ULID, тому останній сценарій з точним набором слів — щойно створений.
        items = _mcp('automations_list', {'botId': INSTAGRAM_BOT_ID}) or []
        wanted = {x.casefold() for x in keywords}
        matches = [x for x in items if {str(v).strip().casefold() for v in
                   (x.get('startMessages') or [])} == wanted]
        if matches:
            new_id = str(sorted(matches, key=lambda x: str(x.get('id') or ''))[-1].get('id') or '')
    if not new_id:
        raise RuntimeError('ChatPlace не повернув ID створеної автоматизації')

    old_paused = False
    try:
        if previous_id and previous_id != new_id:
            _mcp('automations_change_status', {'automationId': previous_id, 'status': 'paused'})
            old_paused = True
        _mcp('automations_change_status', {'automationId': new_id, 'status': 'active'})
    except Exception:
        if old_paused:
            try:
                _mcp('automations_change_status', {'automationId': previous_id, 'status': 'active'})
            except Exception:
                pass
        raise

    rule.chatplace_bot_id = INSTAGRAM_BOT_ID
    rule.chatplace_automation_id = new_id
    rule.chatplace_status = 'active'
    rule.chatplace_error = ''
    rule.synced_at = timezone.now()
    rule.save(update_fields=['chatplace_bot_id', 'chatplace_automation_id', 'chatplace_status',
                             'chatplace_error', 'synced_at', 'updated_at'])
    return {'automation_id': new_id, 'status': 'active', 'link': link}


def pause_in_chatplace(rule):
    if rule.chatplace_automation_id:
        _mcp('automations_change_status', {
            'automationId': rule.chatplace_automation_id, 'status': 'paused'})
    rule.chatplace_status = 'paused'
    rule.chatplace_error = ''
    rule.synced_at = timezone.now()
    rule.save(update_fields=['chatplace_status', 'chatplace_error', 'synced_at', 'updated_at'])
