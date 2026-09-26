# -*- coding: utf-8 -*-
"""Видаткова накладна, яку робить САМА CRM (Олег 26.09.2026).

«Агент має скидати посилання на накладну: він заповнює сделку з товарами і скидає — не потрібно
скидати все текстом, а просто посилання, і в накладній уже буде все прописано.»

Досі накладну збирав фронт (KpDoc.tsx) — тобто тільки менеджер, руками, з відкритої картки.
Тут той самий документ збирається на сервері, тому його може зробити агент у чаті.
Вигляд один в один із тим, що бачить менеджер: QR Instagram, постачальник, таблиця позицій,
сума словами, призначення платежу. Додатково — кнопка «Оплатити карткою», якщо є посилання LiqPay.
"""
from decimal import Decimal

SUP = {
    "name": "ФОП Кріжевські Олег Леонідович",
    "iban": "UA983052990000026002046111493",
    "bank": 'АТ КБ "Приват Банк"',
    "rnukpn": "3031640354",
    "mfo": "305299",
    "phone": "(096) 419-18-90",
    "mail": "mogpod.vipt@gmail.com",
    "ig": "dekor_dlia_stin",
}

_ONES = ["", "одна", "дві", "три", "чотири", "пʼять", "шість", "сім", "вісім", "девʼять"]
_ONES_M = ["", "один", "два", "три", "чотири", "пʼять", "шість", "сім", "вісім", "девʼять"]
_TEENS = ["десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять", "пʼятнадцять",
          "шістнадцять", "сімнадцять", "вісімнадцять", "девʼятнадцять"]
_TENS = ["", "", "двадцять", "тридцять", "сорок", "пʼятдесят", "шістдесят", "сімдесят", "вісімдесят", "девʼяносто"]
_HUNDS = ["", "сто", "двісті", "триста", "чотириста", "пʼятсот", "шістсот", "сімсот", "вісімсот", "девʼятсот"]


def _trio(n, female):
    """Три цифри словами."""
    out = []
    if n // 100:
        out.append(_HUNDS[n // 100])
    n %= 100
    if 10 <= n < 20:
        out.append(_TEENS[n - 10])
    else:
        if n // 10:
            out.append(_TENS[n // 10])
        if n % 10:
            out.append((_ONES if female else _ONES_M)[n % 10])
    return [x for x in out if x]


def _plural(n, forms):
    n = n % 100
    if 10 <= n < 20:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def uah_words(total):
    """«Три тисячі девʼятсот сімдесят одна гривня 00 копійок» — як у паперовій накладній."""
    total = Decimal(str(total or 0))
    whole = int(total)
    kop = int((total - whole) * 100)
    if whole == 0:
        words = ["нуль"]
    else:
        words = []
        mill, thou, rest = whole // 1000000, (whole // 1000) % 1000, whole % 1000
        if mill:
            words += _trio(mill, False) + [_plural(mill, ["мільйон", "мільйони", "мільйонів"])]
        if thou:
            words += _trio(thou, True) + [_plural(thou, ["тисяча", "тисячі", "тисяч"])]
        if rest:
            words += _trio(rest, True)
    s = " ".join(words)
    s = s[:1].upper() + s[1:]
    return "%s %s %02d копійок" % (s, _plural(whole, ["гривня", "гривні", "гривень"]), kop)


def _g(x):
    return ("%.2f" % float(x or 0)).replace(".", ",")


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_invoice_html(deal, pay_url="", title="Видаткова накладна"):
    """HTML накладної для публічного посилання. Той самий вигляд, що й у менеджера (KpDoc.tsx)."""
    from django.utils import timezone
    items = list(deal.items.select_related("product").all())
    rows = []
    for i, it in enumerate(items, 1):
        name = ((it.product.name if it.product_id else "") or getattr(it, "custom_name", "") or "Позиція")
        unit = (getattr(it.product, "unit", "") if it.product_id else "") or "шт"
        rows.append(
            '<tr><td style="border:1px solid #333;padding:4px;text-align:center">%d</td>'
            '<td style="border:1px solid #333;padding:4px">%s</td>'
            '<td style="border:1px solid #333;padding:4px;text-align:center">%s</td>'
            '<td style="border:1px solid #333;padding:4px;text-align:center">%s</td>'
            '<td style="border:1px solid #333;padding:4px;text-align:right">%s</td>'
            '<td style="border:1px solid #333;padding:4px;text-align:right">%s</td></tr>'
            % (i, _esc(name), ("%g" % float(it.quantity or 0)), _esc(unit), _g(it.price), _g(it.total)))
    total = sum((Decimal(str(it.total or 0)) for it in items), Decimal("0"))
    contact = getattr(deal, "contact", None)
    client = _esc(str(contact) if contact else (deal.title or ""))
    phone = _esc(getattr(contact, "phone", "") or "")
    qr = ("https://api.qrserver.com/v1/create-qr-code/?size=130x130&data="
          "https%3A%2F%2Finstagram.com%2F" + SUP["ig"])
    pay_btn = ""
    if pay_url:
        pay_btn = (
            '<div style="margin-top:16px;text-align:center">'
            '<a href="%s" style="display:inline-block;background:#16a34a;color:#fff;text-decoration:none;'
            'font-size:16px;font-weight:bold;padding:13px 26px;border-radius:10px">💳 Оплатити карткою онлайн</a>'
            '<div style="font-size:11px;color:#555;margin-top:6px">Apple Pay, Google Pay, Privat24 або будь-яка '
            'картка. Або за реквізитами нижче.</div></div>' % _esc(pay_url))
    return (
        '<div style="font-family:Arial,sans-serif;color:#111;max-width:720px;margin:0 auto;font-size:13px">'
        '<table style="width:100%%;border-collapse:collapse;margin-bottom:14px"><tr>'
        '<td style="width:150px;vertical-align:top;text-align:center">'
        '<img src="%(qr)s" width="110" height="110" style="display:block;margin:0 auto" '
        'onerror="this.style.display=\'none\'"/>'
        '<div style="font-size:10px;margin-top:3px">@%(ig)s</div>'
        '<div style="font-size:9px;color:#555;margin-top:4px">*Скануй та підпишись!<br/>Знижки та спеціальні '
        'пропозиції<br/>діють тільки для підписників</div></td>'
        '<td style="vertical-align:top;font-size:12px;line-height:1.5">'
        '<b>Постачальник:</b> %(sup)s<br/>IBAN %(iban)s<br/>%(bank)s РНУКПН: %(rnukpn)s; МФО: %(mfo)s<br/>'
        'тел.%(phone_s)s;<br/>mail: %(mail)s<br/><br/>'
        '<b>Отримувач:</b> %(client)s<br/>%(phone_c)s</td>'
        '</tr></table>'
        '<h3 style="text-align:center;margin:10px 0">%(title)s № %(id)s від %(today)s</h3>'
        '<table style="width:100%%;border-collapse:collapse;font-size:12px">'
        '<thead><tr style="background:#fdf6e3">'
        '<th style="border:1px solid #333;padding:4px;width:30px">№</th>'
        '<th style="border:1px solid #333;padding:4px">Товари (роботи, послуги)</th>'
        '<th style="border:1px solid #333;padding:4px;width:55px">Кіл-сть</th>'
        '<th style="border:1px solid #333;padding:4px;width:40px">Од</th>'
        '<th style="border:1px solid #333;padding:4px;width:80px">Ціна</th>'
        '<th style="border:1px solid #333;padding:4px;width:90px">Сума</th>'
        '</tr></thead><tbody>%(rows)s</tbody></table>'
        '<div style="text-align:right;margin-top:10px;font-size:13px">'
        '<div>Всього: <b>%(total)s</b> грн.</div>'
        '<div style="font-size:14px;margin-top:4px">Всього до оплати: <b>%(total)s</b> грн.</div></div>'
        '<div style="margin-top:14px;font-size:12px">%(words)s<br/>У т.ч. ПДВ: Нуль гривень 00 копійок</div>'
        '%(pay)s'
        '<div style="margin-top:16px;border:2px solid #C67D5F;border-radius:10px;padding:12px 14px;background:#fdf3ee">'
        '<div style="font-weight:bold;font-size:14px;color:#8a4b32;margin-bottom:7px">💳 Призначення платежу — '
        'впишіть ТОЧНО цей текст при оплаті на IBAN:</div>'
        '<div style="font-size:15px;font-weight:bold;background:#fff;border:1.5px dashed #C67D5F;border-radius:8px;'
        'padding:9px 12px">Оплата згідно накладної №%(id)s</div>'
        '<div style="font-size:11px;color:#555;margin-top:9px;line-height:1.6"><b style="color:#b45309">Чому це '
        'важливо:</b> без правильного призначення банк не розуміє, за що платіж — ми не бачимо, від кого й за яке '
        'замовлення надійшли гроші, і відправлення затримується.<br/>Коли призначення вказано правильно — ваша '
        'оплата зʼявляється в нас <b>одразу</b>, і ми відразу починаємо готувати замовлення.</div></div></div>'
        % {"qr": qr, "ig": SUP["ig"].upper(), "sup": SUP["name"], "iban": SUP["iban"], "bank": SUP["bank"],
           "rnukpn": SUP["rnukpn"], "mfo": SUP["mfo"], "phone_s": SUP["phone"], "mail": SUP["mail"],
           "client": client, "phone_c": ("тел.: %s" % phone) if phone else "", "title": _esc(title),
           "id": deal.id, "today": timezone.localtime().strftime("%d.%m.%Y"), "rows": "".join(rows),
           "total": _g(total), "words": uah_words(total), "pay": pay_btn})


def invoice_link(deal, pay_url=""):
    """Публічне посилання на накладну (створює або оновлює KpLink сделки)."""
    from .models import KpLink
    from .views import _short_code
    html = build_invoice_html(deal, pay_url=pay_url)
    link = deal.kp_links.order_by("-id").first()
    if link:
        link.html = html
        link.save(update_fields=["html"])
    else:
        code = _short_code()
        while KpLink.objects.filter(code=code).exists():
            code = _short_code()
        link = KpLink.objects.create(code=code, deal=deal, html=html)
    return "https://crm.wallcovdec.com.ua/d/%s/" % link.code
