# -*- coding: utf-8 -*-
"""Видаткова накладна, яку робить САМА CRM (Олег, 26.09.2026).

«Агент має скидати посилання на накладну: він заповнює сделку з товарами і скидає — не потрібно
скидати все текстом, а просто посилання, і в накладній уже буде все прописано.»

Досі накладну збирав фронт (KpDoc.tsx) — тобто тільки менеджер, руками, з відкритої картки.
Тут той самий документ збирається на сервері, тому його може зробити агент у чаті.
26.09.2026: документ адаптований під телефон — на вузькому екрані таблиця розсипається на картки
(«ще потрібно адаптувати під мобільний, накладна не дуже виглядає»).
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

STYLE = """
.wcinv{font-family:Arial,Helvetica,sans-serif;color:#111;max-width:720px;margin:0 auto;font-size:13px}
.wcinv .hdr{display:flex;gap:16px;align-items:flex-start;margin-bottom:14px}
.wcinv .qr{flex:0 0 150px;text-align:center}
.wcinv .qr img{display:block;margin:0 auto}
.wcinv .qr .ig{font-size:10px;margin-top:3px}
.wcinv .qr .sub{font-size:9px;color:#555;margin-top:4px;line-height:1.35}
.wcinv .sup{font-size:12px;line-height:1.55;word-break:break-word}
.wcinv h3{text-align:center;margin:10px 0 4px;font-size:17px}
.wcinv .colr{text-align:center;margin:0 0 10px;font-size:12px;color:#555}
.wcinv table.items{width:100%;border-collapse:collapse;font-size:12px}
.wcinv .items th,.wcinv .items td{border:1px solid #333;padding:5px}
.wcinv .items thead tr{background:#fdf6e3}
.wcinv .items td.no,.wcinv .items td.q,.wcinv .items td.u{text-align:center}
.wcinv .items td.p,.wcinv .items td.s{text-align:right;white-space:nowrap}
.wcinv .tot{text-align:right;margin-top:10px;font-size:13px}
.wcinv .tot .big{font-size:15px;margin-top:4px}
.wcinv .words{margin-top:14px;font-size:12px;color:#333}
.wcinv .paywrap{margin-top:18px;text-align:center}
.wcinv a.pay{display:inline-block;background:#16a34a;color:#fff;text-decoration:none;font-size:17px;
 font-weight:bold;padding:15px 28px;border-radius:12px}
.wcinv .paysub{font-size:11px;color:#555;margin-top:7px}
.wcinv button.reqs{display:inline-block;background:#fff;color:#0f172a;border:2px solid #16a34a;
 font-family:inherit;font-size:15px;font-weight:bold;padding:13px 24px;border-radius:12px;cursor:pointer}
.wcinv button.reqs[disabled],.wcinv button.parts[disabled]{opacity:.65;cursor:default}
.wcinv button.parts{display:inline-block;background:#fff7ed;color:#9a3412;border:2px solid #f59e0b;
 font-family:inherit;font-size:15px;font-weight:bold;padding:13px 24px;border-radius:12px;cursor:pointer}
.wcinv .paywrap+.paywrap{margin-top:10px}
.wcinv .purp{margin-top:18px;border:2px solid #C67D5F;border-radius:10px;padding:12px 14px;background:#fdf3ee}
.wcinv .purp .t{font-weight:bold;font-size:14px;color:#8a4b32;margin-bottom:7px}
.wcinv .purp .code{font-size:15px;font-weight:bold;background:#fff;border:1.5px dashed #C67D5F;
 border-radius:8px;padding:9px 12px;word-break:break-word}
.wcinv .purp .why{font-size:11px;color:#555;margin-top:9px;line-height:1.6}
@media (max-width:620px){
  .wcinv{font-size:13px}
  .wcinv .hdr{flex-direction:column;align-items:center;text-align:center;gap:6px;margin-bottom:8px}
  .wcinv .qr{flex:none}
  .wcinv .qr img{width:72px;height:72px}
  .wcinv .qr .sub{display:none}
  .wcinv .sup{text-align:left;width:100%;font-size:11px;line-height:1.4}
  .wcinv h3{font-size:15px;margin:6px 0 2px}
  .wcinv .items thead{display:none}
  .wcinv table.items,.wcinv .items tbody,.wcinv .items tr,.wcinv .items td{display:block;width:auto}
  .wcinv .items tr{border:1px solid #d5d5d5;border-radius:8px;margin-bottom:7px;padding:7px 9px}
  .wcinv .items td{border:0;padding:0;display:inline;font-size:12px}
  .wcinv .items td:before{content:attr(data-l) ': ';color:#667;font-size:12px}
  .wcinv .items td.no{display:none}
  .wcinv .items td.nm{display:block;font-weight:bold;margin-bottom:3px;font-size:12.5px;line-height:1.3}
  .wcinv .items td.nm:before{content:none}
  .wcinv .items td.q:after{content:' '}
  .wcinv .items td.u{color:#555}
  .wcinv .items td.u:before{content:none}
  .wcinv .items td.p{display:none}
  .wcinv .items td.s{float:right;font-weight:bold}
  .wcinv .items td.s:before{content:none}
  .wcinv .items tr:after{content:'';display:block;clear:both}
  .wcinv a.pay{display:block;font-size:16px;padding:14px 10px}
  .wcinv button.reqs,.wcinv button.parts{display:block;width:100%;font-size:15px;padding:13px 10px}
  .wcinv .purp .why{font-size:10.5px}
}
"""


def _trio(n, female):
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
    kop = int(round((total - whole) * 100))
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


def build_invoice_html(deal, pay_url="", title="Видаткова накладна", note=""):
    """HTML накладної для публічного посилання. Той самий документ, що й у менеджера, але адаптивний."""
    from django.utils import timezone
    items = list(deal.items.select_related("product").all())
    rows = []
    for i, it in enumerate(items, 1):
        name = ((it.product.name if it.product_id else "") or getattr(it, "custom_name", "") or "Позиція")
        unit = (getattr(it.product, "unit", "") if it.product_id else "") or "шт"
        rows.append(
            '<tr><td class="no">%d</td>'
            '<td class="nm">%s</td>'
            '<td class="q" data-l="Кількість">%s</td>'
            '<td class="u" data-l="Одиниця">%s</td>'
            '<td class="p" data-l="Ціна">%s</td>'
            '<td class="s" data-l="Сума">%s грн</td></tr>'
            % (i, _esc(name), ("%g" % float(it.quantity or 0)), _esc(unit), _g(it.price), _g(it.total)))
    total = sum((Decimal(str(it.total or 0)) for it in items), Decimal("0"))
    contact = getattr(deal, "contact", None)
    client = _esc(str(contact) if contact else (deal.title or ""))
    phone = _esc(getattr(contact, "phone", "") or "")
    qr = ("https://api.qrserver.com/v1/create-qr-code/?size=130x130&data="
          "https%3A%2F%2Finstagram.com%2F" + SUP["ig"])
    pay = ''
    if pay_url:
        pay = ('<div class="paywrap"><a class="pay" href="%s">💳 Оплатити карткою онлайн</a>'
               '<div class="paysub">Apple Pay, Google Pay, Privat24 або будь-яка картка.</div>'
               '</div>' % _esc(pay_url))
    # 26.09.2026 (Олег): друга кнопка — клієнт обирає оплату за реквізитами, і CRM надсилає йому
    # в чат той самий текст, що й кнопка менеджера. Диплінків у банки не робимо — у клієнта може
    # бути не Приват, і він заплутається.
    reqs = ('<div class="paywrap"><button type="button" class="reqs" onclick="wcReqs(this)">'
            '🧾 Оплачу за реквізитами</button>'
            '<div class="paysub" id="wcmsg">Надішлемо реквізити й призначення платежу у ваш чат</div>'
            '</div>'
            '<script>function wcReqs(b){b.disabled=true;b.textContent="Надсилаємо…";'
            'var u=location.pathname;if(u.charAt(u.length-1)!=="/")u+="/";'
            'fetch(u+"reqs/",{method:"POST"})'
            '.then(function(r){return r.json()}).then(function(d){'
            'document.getElementById("wcmsg").textContent=d.msg||"Готово";'
            'b.textContent="🧾 Реквізити надіслані"})'
            '.catch(function(){b.disabled=false;b.textContent="🧾 Оплачу за реквізитами";'
            'document.getElementById("wcmsg").textContent="Не вдалось — реквізити нижче в документі"})}'
            '</script>')
    parts = ('<div class="paywrap"><button type="button" class="parts" onclick="wcParts(this)">'
             '🧩 Оплатити частинами — до 10 платежів</button>'
             '<div class="paysub" id="wcparts">Без переплат. Оформлення онлайн за 2 хвилини — '
             'потрібна лише картка Приват24</div></div>'
             '<script>function wcParts(b){b.disabled=true;b.textContent="Готуємо…";'
             'var u=location.pathname;if(u.charAt(u.length-1)!=="/")u+="/";'
             'fetch(u+"parts/",{method:"POST"}).then(function(r){return r.json()}).then(function(d){'
             'if(d.url){location.href=d.url}else{b.disabled=false;'
             'b.textContent="🧩 Оплатити частинами — до 10 платежів";'
             'document.getElementById("wcparts").textContent=d.msg||"Напишіть нам у чат"}})'
             '.catch(function(){b.disabled=false;b.textContent="🧩 Оплатити частинами — до 10 платежів";'
             'document.getElementById("wcparts").textContent="Не вдалось — напишіть нам у чат"})}'
             '</script>')
    return (
        '<div class="wcinv"><style>%(style)s</style>'
        '<div class="hdr"><div class="qr">'
        '<img src="%(qr)s" width="110" height="110" onerror="this.style.display=\'none\'"/>'
        '<div class="ig">@%(ig)s</div>'
        '<div class="sub">*Скануй та підпишись!<br/>Знижки та спеціальні пропозиції<br/>'
        'діють тільки для підписників</div></div>'
        '<div class="sup"><b>Постачальник:</b> %(sup)s<br/>IBAN %(iban)s<br/>'
        '%(bank)s РНУКПН: %(rnukpn)s; МФО: %(mfo)s<br/>тел. %(phone_s)s<br/>mail: %(mail)s<br/><br/>'
        '<b>Отримувач:</b> %(client)s<br/>%(phone_c)s</div></div>'
        '<h3>%(title)s № %(id)s від %(today)s</h3>'
        '%(note)s'
        '<table class="items"><thead><tr>'
        '<th style="width:30px">№</th><th>Товари (роботи, послуги)</th>'
        '<th style="width:55px">Кіл-сть</th><th style="width:40px">Од</th>'
        '<th style="width:80px">Ціна</th><th style="width:90px">Сума</th>'
        '</tr></thead><tbody>%(rows)s</tbody></table>'
        '<div class="tot"><div>Всього: <b>%(total)s</b> грн.</div>'
        '<div class="big">Всього до оплати: <b>%(total)s</b> грн.</div></div>'
        '<div class="words">%(words)s<br/>У т.ч. ПДВ: Нуль гривень 00 копійок</div>'
        '%(pay)s%(parts)s%(reqs)s'
        '<div class="purp"><div class="t">💳 Призначення платежу — впишіть ТОЧНО цей текст '
        'при оплаті на IBAN:</div>'
        '<div class="code">Оплата згідно накладної №%(id)s</div>'
        '<div class="why"><b style="color:#b45309">Чому це важливо:</b> без правильного призначення банк '
        'не розуміє, за що платіж — ми не бачимо, від кого й за яке замовлення надійшли гроші, і '
        'відправлення затримується.<br/>Коли призначення вказано правильно — ваша оплата зʼявляється '
        'в нас <b>одразу</b>, і ми відразу починаємо готувати замовлення.</div></div></div>'
        % {"style": STYLE, "qr": qr, "ig": SUP["ig"].upper(), "sup": SUP["name"], "iban": SUP["iban"],
           "bank": SUP["bank"], "rnukpn": SUP["rnukpn"], "mfo": SUP["mfo"], "phone_s": SUP["phone"],
           "mail": SUP["mail"], "client": client, "phone_c": ("тел.: %s" % phone) if phone else "",
           "title": _esc(title), "id": deal.id, "today": timezone.localtime().strftime("%d.%m.%Y"),
           "note": ('<div class="colr">%s</div>' % _esc(note)) if note else "",
           "rows": "".join(rows), "total": _g(total), "words": uah_words(total), "pay": pay, "reqs": reqs, "parts": parts})


def invoice_link(deal, pay_url="", note=""):
    """Публічне посилання на накладну (створює або оновлює KpLink сделки)."""
    from .models import KpLink
    from .views import _short_code
    html = build_invoice_html(deal, pay_url=pay_url, note=note)
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
