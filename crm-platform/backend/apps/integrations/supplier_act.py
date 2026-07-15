# -*- coding: utf-8 -*-
"""
Розбір накладної постачальника формату «Замовлення покупця» (Корженевський, .xls BIFF).
Колонки: Товар / Кількість / Ціна / Сума без знижки / Знижка / Сума(фінальна).
Закупівельна ціна за од. = Сума / Кількість. Повертає рядки для звірки зі складом.
"""
import re
import xlrd

_UA_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}


def _ua_date(line):
    m = re.search(r"(\d{1,2})\s+([а-яіїєґ']+)\s+(\d{4})", line, re.I)
    if m and m.group(2).lower() in _UA_MONTHS:
        return "%02d.%02d.%s" % (int(m.group(1)), _UA_MONTHS[m.group(2).lower()], m.group(3))
    return None


def _f(v):
    try:
        return float(str(v).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_korzh(file_contents):
    """file_contents — bytes .xls. Повертає dict акта постачальника."""
    wb = xlrd.open_workbook(file_contents=file_contents)
    ws = wb.sheet_by_index(0)
    rows = []
    for r in range(ws.nrows):
        rows.append([str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)])

    out = {"invoice_number": None, "invoice_date": None,
           "supplier": {"name": None, "iban": None, "ipn": None},
           "lines": [], "total": None}
    name_col = qty_col = price_col = sum_col = None
    header_r = None

    for r, row in enumerate(rows):
        line = " ".join(x for x in row if x)
        if not out["invoice_number"]:
            m = re.search(r"Замовлення покупця\s*№\s*(\S+)\s*від\s*(.+?)\s*р", line, re.I)
            if m:
                out["invoice_number"] = m.group(1)
                out["invoice_date"] = _ua_date(m.group(2)) or m.group(2)
        if "Постачальник" in line and not out["supplier"]["name"]:
            # ім'я — у наступних непорожніх клітинках цього ж рядка
            after = [x for x in row if x and "Постачальник" not in x]
            if after:
                out["supplier"]["name"] = after[0][:160]
        m = re.search(r"(UA\d{27})", line)
        if m and not out["supplier"]["iban"]:
            out["supplier"]["iban"] = m.group(1)
        m = re.search(r"ІПН\s*(\d{8,12})", line)
        if m and not out["supplier"]["ipn"]:
            out["supplier"]["ipn"] = m.group(1)
        # шапка таблиці
        if header_r is None and ("Товар" in row and "Кількість" in row):
            for c, val in enumerate(row):
                if val == "Товар":
                    name_col = c
                elif val == "Кількість":
                    qty_col = c
                elif val == "Ціна":
                    price_col = c
                elif "Сума" in val:
                    sum_col = c  # остання "Сума" = фінальна
            header_r = r
            continue
        # рядки товарів
        if header_r is not None and name_col is not None and r > header_r:
            if any(x.startswith("Разом") for x in row):
                out["total"] = _f(row[sum_col]) if (sum_col is not None and sum_col < len(row)) else None
                break
            name = row[name_col] if name_col < len(row) else ""
            qty = _f(row[qty_col]) if (qty_col is not None and qty_col < len(row)) else None
            if name and qty is not None:
                total_line = _f(row[sum_col]) if (sum_col is not None and sum_col < len(row)) else None
                price_unit = round(total_line / qty, 4) if (qty and total_line is not None) else _f(row[price_col] if (price_col is not None and price_col < len(row)) else None)
                out["lines"].append({
                    "name": name,
                    "qty": qty,
                    "price": price_unit,     # закупівельна за одиницю (з урахуванням знижки)
                    "sum": total_line,
                })
    if out["total"] is None and out["lines"]:
        out["total"] = round(sum(l["sum"] or 0 for l in out["lines"]), 2)
    return out


if __name__ == "__main__":
    for f in ("/tmp/korzh_sample_443.xls", "/tmp/korzh_sample_437.xls"):
        import json
        data = open(f, "rb").read()
        print("=" * 40, f)
        print(json.dumps(parse_korzh(data), ensure_ascii=False, indent=1))
