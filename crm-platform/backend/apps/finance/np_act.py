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
