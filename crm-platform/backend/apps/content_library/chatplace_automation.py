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


def direct_message(rule):
    """Text shown in the first Direct card. The URL lives only in its button."""
    text = (rule.reply_text or '').replace('{form_url}', '').replace(
        '{instruction_title}', rule.form.instruction.title).strip()
    text = '\n'.join(line.rstrip() for line in text.splitlines())
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    return text


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
    # Адреса вже є в кнопці. Маркер лишається сумісним зі старими текстами,
    # але ніколи не розгортається у довгий URL всередині Direct-повідомлення.
    direct_text = direct_message(rule)
    if not direct_text:
        raise ValueError('Додайте текст повідомлення в Direct')
    args = {
        'botId': INSTAGRAM_BOT_ID,
        'triggerType': triggers,
        'startMessages': keywords,
        'templateType': 'base',
        'welcomeMessage': direct_text,
        'welcomeButton': 'Отримати техкарту',
        'messageWithLink': 'Оберіть канал і залиште один контакт — техкарта відкриється одразу.',
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

    # Quick Setup створює зайвий проміжний крок. Перша кнопка має одразу
    # відкривати коротку форму, тому перетворюємо її на URL-кнопку і
    # від'єднуємо друге повідомлення. Публічна відповідь на коментар,
    # створена Quick Setup через autoAnswers, при цьому зберігається.
    try:
        detail = _mcp('automations_get_detail', {'automationId': new_id}) or {}
        first = next((m for step in (detail.get('steps') or [])
                      for m in (step.get('messages') or []) if m.get('isFirstMessage')), None)
        button = (first.get('inlineButtons') or [None])[0] if first else None
        if not first or not first.get('id') or not button or not button.get('id'):
            raise RuntimeError('ChatPlace не повернув перше повідомлення або кнопку автоматизації')
        _mcp('automations_messages_update', {
            'messageId': first['id'], 'text': direct_text})
        _mcp('automations_inline_buttons_update', {
            'buttonId': button['id'], 'text': 'Отримати техкарту', 'url': link})
        _mcp('automations_buttons_connect', {'buttonId': button['id']})
    except Exception:
        try:
            _mcp('automations_change_status', {'automationId': new_id, 'status': 'paused'})
        except Exception:
            pass
        raise

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
