# -*- coding: utf-8 -*-
"""Коментар під постом/рекламою → CRM сама пише клієнту в Direct (Олег, 23.09.2026).

«Якщо переводимо діалог у Direct і кажемо, що скинемо фото — фото і інформація мають реально прийти.
І в самому Direct не писати "напишу в директ" — це нелогічно, ми вже в директі.»

Як працює: клієнт написав у коментарі тригерне слово («Галатея», «шовк», назву матеріалу) →
Instagram дозволяє один раз відповісти цьому коментатору приватно (private reply) →
CRM надсилає знайомство + що це за матеріал + ціну тест-набору «від» + сторінку кольорів.
Фото підтягуються самі: у тексті є посилання на сторінку матеріалу, і echo цього повідомлення
запускає звичайний механізм (apps/inbox/ai_handoff.py) — той надсилає 2-3 фото в інтерʼєрі.
"""
import re

from django.utils import timezone

MARK = "Direct у відповідь на коментар"
SHORT = {
    1623: "сяючі перламутрові піщинки з мʼяким відблиском",
    1620: "перламутрові піщинки з делікатним блиском",
    1610: "мокрий шовк із мʼяким перламутровим переливом",
    1611: "біло-перламутровий мокрий шовк",
    1630: "шовк із благородним блиском",
    1631: "шовк із матовим переливом",
    1614: "шовкове покриття з іскринками",
    1615: "матове покриття з шовково-бархатистим ефектом",
    1649: "дрібнозерниста перламутрова штукатурка «Вельвет Луна»",
    1647: "перламутрово-біла «Вельвет Луна»",
    1650: "структурний перламутровий марморин «Вельвет Люкс»",
    1639: "фактурна штукатурка «Патера» — травертин, марморин, арт-бетон",
    1641: "дрібнозерниста «Патера Мікро»",
    1640: "крупнозерниста «Патера Гросе»",
}
KIT_RX = {
    1623: r"galateya", 1620: r"eleganti", 1617: r"eleganti", 1618: r"eleganti", 1619: r"eleganti",
    1610: r"sirena silk", 1611: r"sirena silk bianco", 1642: r"sirena silk", 1643: r"sirena silk",
    1630: r"mermi silk", 1631: r"mermi silk мат", 1614: r"celestia", 1615: r"celestial mat",
    1649: r"velvet luna", 1647: r"velvet luna bianco", 1648: r"velvet luna",
    1650: r"velvet lux", 1639: r"травертин", 1641: r"pattera micro", 1640: r"травертин",
}


def kit_from_price(product_id):
    """Ціна тест-набору «від» — з каталогу CRM (найдешевший варіант набору цього матеріалу)."""
    from apps.warehouse.models import Product
    rx = KIT_RX.get(product_id)
    if not rx:
        return None
    qs = (Product.objects.filter(is_active=True, name__iregex=rx, price__gt=0)
          .filter(name__iregex=r"тестов|тест-набір|тестовий набір").order_by("price"))
    p = qs.first()
    return p.price if p else None


def compose(texts, extra=""):
    """Текст першого повідомлення в Direct або None, якщо не зрозуміли матеріал."""
    from apps.knowledge.volume_calc import COLORS, COLORS_BY_ID, find_material
    mat = find_material(texts, extra)
    if not mat:
        return None
    pid, base = mat
    url = COLORS_BY_ID.get(pid, COLORS.get(base, ""))
    if not url:
        return None
    short = SHORT.get(pid, "декоративне покриття Wallcov")
    price = kit_from_price(pid)
    line = ("Тест-набір від %s грн — можна спробувати нанесення і побачити колір наживо.\n"
            % ("%g" % float(price))) if price else ""
    return ("Вітаю! Мене звати Юля 😊 Дякую за інтерес до нашого покриття.\n"
            "%s — %s.\n%s"
            "Ось кольори, фото в інтерʼєрі й відео: %s\n\n"
            "Для якого приміщення розглядаєте?" % (_title(pid), short, line, url))


def _title(pid):
    from apps.warehouse.models import Product
    p = Product.objects.filter(id=pid).values_list("name", flat=True).first() or ""
    return re.split(r"[.,(]| \d", p)[0].strip()[:40] or "Покриття"


def already_sent(conv):
    from .models import Message
    return Message.objects.filter(conversation=conv, internal=True, text__contains=MARK).exists()


def maybe_send(conv, comment_id, comment_text):
    """Відповісти коментатору приватно в Direct. Один раз на коментар."""
    from . import meta
    from .models import Message
    try:
        if not comment_id or already_sent(conv):
            return False
        from .ai_reply import channel_on
        if not channel_on(conv.channel):
            return False
        card = (conv.config or {}).get("source_card") or {}
        texts = [comment_text or "", card.get("caption") or ""]
        text = compose(texts)
        if not text:
            return False
        meta.private_reply(str(comment_id), text)
        Message.objects.create(conversation=conv, direction="out", internal=True,
                               text="%s: надіслав знайомство, ціну і сторінку кольорів (фото підуть окремо)." % MARK,
                               sender_name="CRM", created_at=timezone.now())
        return True
    except Exception as e:
        try:
            Message.objects.create(conversation=conv, direction="out", internal=True,
                                   text="%s: не вдалося надіслати (%s)." % (MARK, str(e)[:200]),
                                   sender_name="CRM")
        except Exception:
            pass
        return False
