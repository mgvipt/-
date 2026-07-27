# -*- coding: utf-8 -*-
"""
Розбір акта Нової Пошти (пара файлів xlsx: Специфікація + опц. Рахунок-фактура).
Повертає структуру для створення КРЕДИТОРКИ (PlannedPayment payable) + деталізацію
відправлень по ЕН для рознесення собівартості доставки по сделкам.

Специфікація самодостатня (містить № акта, договір, ЄДРПОУ, всі ЕН і Разом).
Рахунок-фактура додає IBAN, ПДВ та дату у форматі dd.mm.yyyy.
Приймає file-like об'єкти (request.FILES) або шляхи.
"""
import re
import openpyxl

_UA_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}


def _num(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _cells(row):
    return [str(v).strip() for v in row if v is not None and str(v).strip()]


def _rows(f):
    wb = openpyxl.load_workbook(f, data_only=True, read_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _parse_ua_date(line):
    """'від 10 липня 2026' -> '10.07.2026'"""
    m = re.search(r"(\d{1,2})\s+([а-яіїєґ']+)\s+(\d{4})", line, re.I)
    if m and m.group(2).lower() in _UA_MONTHS:
        return "%02d.%02d.%s" % (int(m.group(1)), _UA_MONTHS[m.group(2).lower()], m.group(3))
    return None


def parse_specifikacia(f):
    rows = _rows(f)
    out = {"invoice_number": None, "invoice_date": None, "contract": None,
           "edrpou": None, "iban": None, "shipments": [], "total": None}
    header_idx = None
    for i, row in enumerate(rows):
        cs = _cells(row)
        line = " ".join(cs)
        m = re.search(r"акту[^№]*№\s*(\S+)", line, re.I)
        if m and not out["invoice_number"]:
            out["invoice_number"] = m.group(1).strip()
            d = _parse_ua_date(line)
            if d:
                out["invoice_date"] = d
        m = re.search(r"договір\s*№?\s*(\d+)\s*від\s*([\d.]+)", line, re.I)
        if m and not out["contract"]:
            out["contract"] = {"number": m.group(1), "date": m.group(2)}
        m = re.search(r"ЄДРПОУ[:\s]*(\d{8})", line)
        if m and not out["edrpou"]:
            out["edrpou"] = m.group(1)
        m = re.search(r"(UA\d{27})", line)
        if m and not out["iban"]:
            out["iban"] = m.group(1)
        if cs and cs[0] == "№ з/п":
            header_idx = i
            continue
        if header_idx is None:
            continue
        if cs and cs[0] == "Разом":
            nums = [x for x in (_num(c) for c in cs) if x is not None]
            out["total"] = nums[-1] if nums else None
            break
        if cs and re.fullmatch(r"\d+", cs[0]) and len(cs) >= 6 and re.fullmatch(r"\d{10,18}", cs[1]):
            out["shipments"].append({
                "n": cs[0], "ttn": cs[1],
                "date": cs[2] if len(cs) > 2 else None,
                "route": cs[3] if len(cs) > 3 else None,
                "cost": _num(cs[-1]),
            })
    return out


def parse_rahunok(f):
    rows = _rows(f)
    out = {"invoice_number": None, "invoice_date": None, "contract": None,
           "edrpou": None, "iban": None, "ipn": None,
           "total_no_vat": None, "vat": None, "total_with_vat": None, "services": []}
    for row in rows:
        cs = _cells(row)
        line = " ".join(cs)
        m = re.search(r"ЄДРПОУ\s*(\d{8})", line)
        if m and not out["edrpou"]:
            out["edrpou"] = m.group(1)
        m = re.search(r"(UA\d{27})", line)
        if m and not out["iban"]:
            out["iban"] = m.group(1)
        m = re.search(r"договір\s*№?\s*(\d+)\s*від\s*([\d.]+)", line, re.I)
        if m and not out["contract"]:
            out["contract"] = {"number": m.group(1), "date": m.group(2)}
        m = re.search(r"Рахунок-фактура\s*№\s*(\S+)", line)
        if m and not out["invoice_number"]:
            out["invoice_number"] = m.group(1)
        m = re.search(r"від\s+([\d.]{8,10})\s*р", line)
        if m and not out["invoice_date"]:
            out["invoice_date"] = m.group(1)
        if "Разом без ПДВ" in line:
            out["total_no_vat"] = _num(cs[-1])
        elif "Всього з ПДВ" in line:
            out["total_with_vat"] = _num(cs[-1])
        elif cs and cs[0] == "ПДВ:" and out["vat"] is None:
            out["vat"] = _num(cs[-1])
        if cs and re.fullmatch(r"\d+", cs[0]) and len(cs) >= 3 and len(cs[1]) > 8:
            amt = _num(cs[-1])
            if amt is not None:
                out["services"].append({"name": cs[1], "amount": amt})
    return out


def parse_act(spec_file, rahunok_file=None):
    """Головна функція. Пріоритет: рахунок для шапки (дата/ПДВ/IBAN), специфікація для ЕН."""
    spec = parse_specifikacia(spec_file)
    rah = parse_rahunok(rahunok_file) if rahunok_file is not None else {}

    def pick(*vals):
        for v in vals:
            if v:
                return v
        return None

    amount = pick(rah.get("total_with_vat"), spec.get("total"))
    invoice_number = pick(rah.get("invoice_number"), spec.get("invoice_number"))
    invoice_date = pick(rah.get("invoice_date"), spec.get("invoice_date"))
    contract = pick(rah.get("contract"), spec.get("contract"))
    edrpou = pick(rah.get("edrpou"), spec.get("edrpou"))
    iban = pick(rah.get("iban"), spec.get("iban"))

    items_sum = round(sum(s["cost"] or 0 for s in spec["shipments"]), 2)
    checks = {
        "amount": amount,
        "spec_total": spec.get("total"),
        "spec_items_sum": items_sum,
        "items_match_total": (amount is not None and items_sum == round(amount, 2)),
    }
    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "contract": contract,
        "amount": amount,
        "vat": rah.get("vat"),
        "total_no_vat": rah.get("total_no_vat"),
        "counterparty": {"name": 'ТОВ "Нова Пошта"', "edrpou": edrpou, "iban": iban},
        "service_lines": rah.get("services") or [],
        "shipments": spec["shipments"],
        "checks": checks,
    }


def create_kreditorka_from_act(act, user=None):
    """Створює кредиторку (PlannedPayment payable) з розібраного акта НП + рознесення доставки
    по сделкам (Deal.np_data, без грошової операції). Ідемпотентно за № акта.
    Спільна логіка для ручного завантаження і підтвердження з пошти."""
    from .models import PlannedPayment, FinModelArticle
    from apps.crm.models import Deal
    from django.utils import timezone as _tz
    import datetime as _dt

    inv = act.get("invoice_number")
    amount = act.get("amount")
    if not inv or not amount:
        return {"error": "no_invoice_or_amount"}
    existing = PlannedPayment.objects.filter(kind="payable", comment__icontains=inv).exclude(status__in=["canceled", "rejected"]).first()
    if existing:
        return {"already": True, "payable_id": existing.id, "invoice_number": inv}
    fund = FinModelArticle.objects.filter(name="Логістика / доставка", active=True).first()
    due = None
    if act.get("invoice_date"):
        try:
            due = _dt.datetime.strptime(act["invoice_date"], "%d.%m.%Y").date()
        except ValueError:
            due = None
    due = due or _tz.localdate()
    cp = act.get("counterparty") or {}
    detail = "ЄДРПОУ %s · IBAN %s" % (cp.get("edrpou") or "?", cp.get("iban") or "?")
    ship = act.get("shipments") or []
    # контакт-постачальник (щоб контрагент був клікабельним у Дт/Кт)
    from apps.crm.models import Contact as _Contact
    contact = None
    edrpou = (cp.get("edrpou") or "").strip()
    cp_name = (cp.get("name") or "Нова Пошта").strip()
    if edrpou:
        contact = _Contact.objects.filter(edrpou=edrpou).first()
    if contact is None and edrpou:
        contact = _Contact.objects.create(first_name=cp_name[:120], edrpou=edrpou, iban=(cp.get("iban") or ""))
    pp = PlannedPayment.objects.create(
        kind="payable", amount=amount, due_date=due,
        counterparty=(cp.get("name") or "Нова Пошта")[:160], contact=contact,
        fin_article=fund, status="planned",
        comment=("Нова Пошта · акт %s від %s · договір %s · %d відправлень · %s" % (
            inv, act.get("invoice_date") or "?", (act.get("contract") or {}).get("number", "?"),
            len(ship), detail))[:255])
    deals_updated = 0
    matched = 0
    for s in ship:
        ttn = s.get("ttn")
        d = Deal.objects.filter(ttn=ttn).first() if ttn else None
        if not d:
            continue
        matched += 1
        nd = d.np_data if isinstance(d.np_data, dict) else {}
        acts = nd.get("delivery_acts") or []
        if any(a.get("act") == inv and a.get("ttn") == ttn for a in acts):
            continue
        acts.append({"act": inv, "ttn": ttn, "cost": s.get("cost"), "date": s.get("date"), "route": s.get("route")})
        nd["delivery_acts"] = acts
        nd["delivery_cost_total"] = round(sum(a.get("cost") or 0 for a in acts), 2)
        d.np_data = nd
        d.save(update_fields=["np_data"])
        deals_updated += 1
    return {"payable_id": pp.id, "deals_updated": deals_updated, "matched": matched,
            "amount": amount, "invoice_number": inv, "shipments": len(ship)}
