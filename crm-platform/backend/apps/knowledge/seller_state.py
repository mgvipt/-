"""Persistent, source-linked explicit choices. Never infer payment or image content."""
import re
from django.db import transaction

KEY = 'seller_state_v1'
SELECT = re.compile(r'тепер|теперь|обираю|обрала|обрав|выбираю|выбрала|выбрал|беру|беремо|замовляю|заказываю|зупинил\w* на|остановил\w* на', re.I)
RESET = re.compile(r'новий (?:об.?єкт|проект|будинок)|новый (?:объект|проект|дом)|інш\w* (?:квартир|об.?єкт|проект|будинок)|друг\w* (?:квартир|объект|проект|дом)', re.I)


def reduce_message(state, msg):
    from .conversation_context import COLOR
    from .volume_calc import find_material
    t = (msg.text or '').strip()
    state['through_id'] = msg.pk
    if msg.direction != 'in':
        return
    if RESET.search(t):
        state['fields'] = {}
        state['project_start_id'] = msg.pk
    fields = state.setdefault('fields', {})
    def save(k, value):
        fields[k] = {'value': value, 'message_id': msg.pk, 'quote': t[:500]}
    # Questions and comparisons are evidence, never a committed selection.
    selecting = bool(SELECT.search(t) or RESET.search(t)) and '?' not in t and not re.search(r'\b(?:не|ні|нет|або|или|чи)\b', t, re.I)
    if selecting:
        mat = find_material([t])
        if mat and not re.search(r'\b(?:або|или|чи|не)\b', t, re.I):
            prior = fields.get('material',{}).get('value',{}).get('product_id')
            if prior and prior != mat[0]:
                fields.pop('color',None)
            save('material', {'product_id': mat[0], 'system': mat[1]})
    codes = COLOR.findall(t)
    if len(codes) == 1 and (selecting or COLOR.fullmatch(t) or re.fullmatch(r'(?:колір|цвет|код)\s*[:—-]?\s*'+re.escape(codes[0]), t, re.I)):
        save('color', codes[0])
    area = re.search(r'(?:площа|площадь)\s+(?:стін|стен)\s*[:—-]?\s*(\d+(?:[.,]\d+)?)\s*(?:м²|м2|кв)', t, re.I)
    if not area and selecting:
        area = re.search(r'на\s+(\d+(?:[.,]\d+)?)\s*(?:м²|м2|кв)', t, re.I)
    if not area and 'wall_area_m2' in fields:
        area = re.fullmatch(r'(?:тепер|теперь)?\s*(\d+(?:[.,]\d+)?)\s*(?:м²|м2|кв\.?м)', t, re.I)
    if area and '?' not in t:
        save('wall_area_m2', area[1].replace(',', '.'))
    if '?' not in t:
        for key, no, yes in [
            ('board', r'без\s+(?:дощеч|досоч)|(?:дощеч|досоч)\w*\s+не\s+(?:потріб|нуж)', r'(?:з|із|с)\s+(?:дощеч|досоч)'),
            ('tint', r'без\s+(?:тонув|колеров)', r'(?:з|із|с)\s+(?:тонув|колеров)'),
            ('deep_primer_available', r'(?:глибок|глубок)\w*\s+ґ?г?рунт\w*\s+(?:немає|нет)|ґ?г?рунт\w*\s+(?:глибок|глубок)[^.!?]{0,35}(?:немає|нет)', r'(?:глибок|глубок)\w*\s+ґ?г?рунт\w*\s+(?:є|есть)|ґ?г?рунт\w*\s+(?:глибок|глубок)[^.!?]{0,35}(?:є|есть)')]:
            if re.search(no,t,re.I): save(key,False)
            elif re.search(yes,t,re.I): save(key,True)
    if re.search(r'(?:глибок|глубок)',t,re.I) and '?' not in t:
        save('deep_primer_request',t)
    if msg.attachments:
        save('last_client_attachment', {'pixels_read': False})


def refresh(conv, incoming):
    """Incremental replay into a namespaced key, merging under a row lock."""
    from apps.inbox.models import Conversation, Message
    with transaction.atomic():
        row = Conversation.objects.select_for_update().get(pk=conv.pk)
        cfg = dict(row.config or {})
        state = dict(cfg.get(KEY) or {'fields': {}, 'through_id': 0})
        # Historical preview must not consume evidence from the future.
        if state.get('through_id',0) > incoming.pk:
            state = {'fields': {}, 'through_id': 0}
            persist = False
        else:
            persist = True
        qs = Message.objects.filter(conversation_id=conv.pk,internal=False,id__gt=state.get('through_id',0),id__lte=incoming.pk).order_by('id')
        for msg in qs.iterator(chunk_size=300):
            reduce_message(state,msg)
        if persist:
            cfg[KEY] = state
            row.config = cfg; row.save(update_fields=['config'])
            conv.config = cfg
        return state


def active_order(conv):
    """No arbitrary 'latest' when several orders exist; no web contact-wide lookup."""
    from apps.crm.models import Deal
    if not conv.contact_id or conv.channel.kind == 'web':
        return None, False
    orders = Deal.objects.filter(contact_id=conv.contact_id,stage__is_won=False,stage__is_lost=False,items__isnull=False).distinct()
    ids = list(orders.values_list('id',flat=True)[:2])
    return (orders.get(pk=ids[0]),False) if len(ids)==1 else (None,len(ids)>1)


def action_blocked(conv):
    order, ambiguous = active_order(conv)
    if (conv.config or {}).get('seller_acceptance_test'):
        return 'Тест власника: фінансові дії вимкнені, перевірте чернетку замовлення.'
    if ambiguous:
        return 'Кілька відкритих замовлень: уточніть потрібне, автоматичне оформлення зупинено.'
    if order and any(p.is_paid and p.amount > 0 for p in order.payments.all()):
        return 'У поточному замовленні є оплата: зміни та доплату погоджує менеджер; повторне оформлення зупинено.'
    return ''
