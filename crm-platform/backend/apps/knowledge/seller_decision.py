"""Shared response planning; never sends messages or creates orders."""
from .models import KnowledgeSettings
from .volume_calc import for_dialog, prompt_block, language_hint, final_quote_reply
from .answer import answer

HELLO = ("ПЕРШИЙ КОНТАКТ у цьому чаті: почни просто — «Вітаю! Мене звати Юля 😊» (без посади і назви "
         "компанії), далі коротко по суті запиту і ОРІЄНТИР ЦІНИ (ціна тест-набору або за 1 м², "
         "залежно від питання). Одне відкрите питання лише якщо бракує даних. Фото матеріалу і сторінку кольорів CRM "
         "надішле окремим повідомленням — не дублюй їх у своєму тексті. Далі в діалозі не вітайся.")


def decide(messages, saved_selection, incoming_text, *, first=False, ad_context="", ad_query="",
           crm_context="", action_hold="", contact_id=None, estimate_only=False, source="Тест продавця CRM"):
    quotes = [v["quote"] for k,v in sorted(saved_selection.get("fields", {}).items(), key=lambda kv:kv[1]["message_id"])
              if k in ("material", "wall_area_m2", "color", "deep_primer_request")]
    calc_messages = [{"role":"client", "text":q} for q in dict.fromkeys(quotes)] + [m for m in messages if m.get("role")=="client"]
    try:
        calc = for_dialog(calc_messages, ad_query)
    except Exception:
        calc = None
    try:
        from .colors import prompt_block as color_block
        color_context = color_block(incoming_text)
    except Exception:
        color_context = ""
    context = "\n\n".join(x for x in (ad_context, prompt_block(calc), color_context, language_hint(incoming_text),
        HELLO if first else "", crm_context,
        ("ОФОРМЛЕННЯ ЗУПИНЕНО: " + action_hold + " Не обіцяй створений рахунок/посилання. Покажи склад як чернетку.") if action_hold else "") if x)
    own_deep = saved_selection.get("fields", {}).get("deep_primer_available", {}).get("value") is True
    result = None if estimate_only else final_quote_reply(calc, incoming_text, deep_available=own_deep)
    if result is None:
        result = answer("yulia_web", messages, include_drafts=False,
            model=KnowledgeSettings.get().webchat_model or None, source=source,
            timeout=25, context=context, context_query=ad_query, contact_id=contact_id, estimate_only=estimate_only)
    return result, calc


def volume_invoice_lines(calc, order):
    """Trusted invoice composition shared by production and preview."""
    if not calc or not calc.get('ok') or calc.get('missing'):
        return None
    lines=list(calc['lines'])+list(calc.get('tara_lines') or [])
    tint=calc.get('tint') if order.get('tint',True) else None
    if order.get('tint',True) and (not tint or tint.get('need_color') or tint.get('total') is None):
        return None
    if tint:
        from .volume_calc import TINT_PRODUCT
        lines.append({'product_id':TINT_PRODUCT,'name':'Тонування','qty':1,'price':tint['total']})
    return lines
