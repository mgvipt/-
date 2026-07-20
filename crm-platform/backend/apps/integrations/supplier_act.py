# -*- coding: utf-8 -*-
"""Розбір накладної/рахунку постачальника (.xls BIFF / .xlsx).
Підтримує різні формати (Корженевський «Замовлення покупця», Єлдинов «Рахунок на оплату» тощо):
шапка таблиці зіставляється НЕЧІТКО (Товар* / Кіл* / Ці* / Сума), колонки — за позицією в шапці.
Закупівельна ціна за од. = Сума / Кількість (або колонка «Ціна»). Повертає рядки для звірки зі складом.
"""
import re

_UA_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}


def _ua_date(line):
    m = re.search(r"(\d{1,2})\s+([а-яіїєґ']+)\s+(\d{4})", line, re.I)
    if m and m.group(2).lower() in _UA_MONTHS:
        return "%02d.%02d.%s" % (int(m.group(1)), _UA_MONTHS[m.group(2).lower()], m.group(3))
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", line)
    if m:
        return "%02d.%02d.%s" % (int(m.group(1)), int(m.group(2)), m.group(3))
    return None


def _f(v):
    try:
        return float(str(v).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _rows_from_bytes(data):
    """Читає .xls (BIFF, xlrd) або .xlsx (openpyxl). Повертає список рядків (список клітинок-рядків)."""
    if data[:4] == b"\xd0\xcf\x11\xe0":  # OLE2 = старий .xls
        import xlrd
        wb = xlrd.open_workbook(file_contents=data)
        ws = wb.sheet_by_index(0)
        return [[str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)] for r in range(ws.nrows)]
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.active
    out = []
    for row in ws.iter_rows(values_only=True):
        out.append(["" if v is None else str(v).strip() for v in row])
    return out


# слова, що позначають кінець таблиці товарів
_END_MARKERS = ("Разом", "Всього до", "Всьго до", "Без податку", "ПДВ", "Всього наймен")


def parse_korzh(file_contents):
    """file_contents — bytes .xls/.xlsx. Повертає dict акта постачальника."""
    rows = _rows_from_bytes(file_contents)

    out = {"invoice_number": None, "invoice_date": None,
           "supplier": {"name": None, "iban": None, "ipn": None},
           "lines": [], "total": None}
    name_col = qty_col = price_col = sum_col = code_col = None
    header_r = None

    for r, row in enumerate(rows):
        line = " ".join(x for x in row if x)

        # ── номер накладної/рахунку (різні формулювання) ──
        if not out["invoice_number"]:
            m = re.search(r"(?:Рахунок на оплату|Замовлення покупця|Видаткова накладна|Накладна|Рахунок)\s*№\s*([^\s,]+)", line, re.I)
            if m:
                out["invoice_number"] = m.group(1)
                out["invoice_date"] = _ua_date(line)

        # ── постачальник (Постачальник / Одержувач) ──
        if not out["supplier"]["name"] and ("Постачальник" in line or "Одержувач" in line):
            m2 = re.search(r"(?:Постачальник|Одержувач)\s*:?\s*(.+)", line)
            if m2:
                nm = re.split(r",|ІПН|ЄДРПОУ|ДРФО|р/р|IBAN|UA\d", m2.group(1))[0].strip()
                if nm and len(nm) >= 4:
                    out["supplier"]["name"] = nm[:160]
        m = re.search(r"(UA\d{27})", line)
        if m and not out["supplier"]["iban"]:
            out["supplier"]["iban"] = m.group(1)
        m = re.search(r"(?:ІПН|ЄДРПОУ|ДРФО)\s*(\d{8,12})", line)
        if m and not out["supplier"]["ipn"]:
            out["supplier"]["ipn"] = m.group(1)

        # ── підсумок із фрази "на суму X грн" (найнадійніше) ──
        m = re.search(r"на суму\s+([\d\s.,]+)\s*грн", line, re.I)
        if m and out["total"] is None:
            out["total"] = _f(m.group(1))

        # ── шапка таблиці (нечітке зіставлення) ──
        if header_r is None:
            has_name = any(str(v).strip().startswith("Товар") for v in row)
            has_qty = any("Кіл" in str(v) for v in row)
            if has_name and has_qty:
                for c, val in enumerate(row):
                    vs = str(val).strip()
                    if name_col is None and vs.startswith("Товар"):
                        name_col = c
                    elif qty_col is None and "Кіл" in vs:
                        qty_col = c
                    elif vs == "Код":
                        code_col = c
                    elif price_col is None and vs.startswith("Ці"):
                        price_col = c
                    elif "Сума" in vs:
                        sum_col = c  # остання «Сума»
                header_r = r
                continue

        # ── рядки товарів ──
        if header_r is not None and name_col is not None and r > header_r:
            if any(str(x).startswith(_END_MARKERS) for x in row):
                if out["total"] is None:
                    nums = [_f(x) for x in row if _f(x) is not None]
                    if nums:
                        out["total"] = nums[-1]
                break
            name = row[name_col] if name_col < len(row) else ""
            qty = _f(row[qty_col]) if (qty_col is not None and qty_col < len(row)) else None
            if name and qty is not None:
                sm = _f(row[sum_col]) if (sum_col is not None and sum_col < len(row)) else None
                pr = _f(row[price_col]) if (price_col is not None and price_col < len(row)) else None
                if pr is None and sm is not None and qty:
                    pr = round(sm / qty, 4)
                if sm is None and pr is not None:
                    sm = round(pr * qty, 2)
                out["lines"].append({"name": name, "qty": qty, "price": pr, "sum": sm})

    if out["total"] is None and out["lines"]:
        out["total"] = round(sum(l["sum"] or 0 for l in out["lines"]), 2)
    return out


if __name__ == "__main__":
    import sys
    import json
    data = open(sys.argv[1], "rb").read()
    print(json.dumps(parse_korzh(data), ensure_ascii=False, indent=1))
