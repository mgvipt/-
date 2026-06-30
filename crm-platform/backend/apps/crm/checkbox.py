"""Checkbox-клієнт CRM (нативний, stdlib urllib) — фіскальні чеки ДПС.
Логіка як у finmap fiscal/checkbox.py: signin(PIN) → ensure_shift → receipt.
Аванс-чек (prepayment) якщо оплата < суми товарів; інакше sell-чек (повний).
Фінальний чек по авансу звʼязується через pre_payment_relation_id (для податкової)."""
import json
import time
import urllib.request
import urllib.error
from django.conf import settings


class CheckboxError(Exception):
    pass


def _base():
    return (getattr(settings, "CHECKBOX_API_BASE", "") or "https://api.checkbox.in.ua").rstrip("/")


def _req(method, path, token=None, body=None, extra_headers=None):
    url = _base() + path
    headers = {
        "Content-Type": "application/json",
        "X-License-Key": getattr(settings, "CHECKBOX_LICENSE_KEY", ""),
        "X-Client-Name": "Wallcov-CRM",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read()[:500].decode("utf-8", "ignore") if e.fp else ""
        raise CheckboxError("HTTP %s %s :: %s" % (e.code, path, detail))
    except urllib.error.URLError as e:
        raise CheckboxError("URL error %s: %s" % (path, e))


def signin():
    d = _req("POST", "/api/v1/cashier/signinPinCode", body={"pin_code": getattr(settings, "CHECKBOX_PASSWORD", "")})
    tok = d.get("access_token")
    if not tok:
        raise CheckboxError("Немає access_token у відповіді signin")
    return tok


def get_shift(token):
    try:
        d = _req("GET", "/api/v1/cashier/shift", token=token)
    except CheckboxError as e:
        if "HTTP 404" in str(e):
            return None
        raise
    if d and d.get("status") in ("CREATED", "OPENING", "OPENED"):
        return d
    return None


def ensure_shift(token):
    sh = get_shift(token)
    if sh and sh.get("status") == "OPENED":
        return sh
    if sh is None:
        _req("POST", "/api/v1/shifts", token=token, body={})
    for _ in range(20):  # чекаємо OPENED до 10с (відкриття асинхронне через ДПС)
        sh = get_shift(token)
        if sh and sh.get("status") == "OPENED":
            return sh
        time.sleep(0.5)
    raise CheckboxError("Зміна Checkbox не перейшла в OPENED за 10с")


def create_receipt(goods, amount_kopecks, external_id, payment_method="CASHLESS", payment_label=None,
                   advance=False, client_name=None, relation_id=None, ttn=None):
    """Створити чек. advance=True → аванс-чек (часткова оплата); False → повний sell.
    Якщо relation_id заданий → закриваюче/додаткове по тому ж prepayment-ланцюгу."""
    token = signin()
    ensure_shift(token)
    body = {
        "external_id": external_id,
        "goods": goods,
        "payments": [dict({"type": payment_method, "value": amount_kopecks}, **({"label": payment_label} if payment_label else {}))],
    }
    if client_name:
        body["client_full_name"] = client_name[:120]
    if ttn:
        body["related_shipping"] = {"provider": "nova_poshta", "ttn": ttn, "enable_payment_control": True}

    if advance:
        body["prepayment_amount"] = amount_kopecks
        extra = {"pre_payment_relation_id": relation_id} if relation_id else None
        d = _req("POST", "/api/v1/prepayment-receipts", token=token, body=body, extra_headers=extra)
    elif relation_id:
        # закриваючий чек авансового ланцюга
        d = _req("POST", "/api/v1/prepayment-receipts/%s" % relation_id, token=token, body=body)
    else:
        d = _req("POST", "/api/v1/receipts/sell", token=token, body=body)

    rid = str(d.get("id") or "")
    url = d.get("tax_url") or d.get("url") or ""
    fiscal = d.get("fiscal_code")
    # Checkbox фіскалізує асинхронно — чекаємо tax_url/DONE (до ~13с)
    if rid and not url:
        for _ in range(11):
            time.sleep(1.2)
            try:
                rr = _req("GET", "/api/v1/receipts/%s" % rid, token=token)
            except CheckboxError:
                continue
            st = rr.get("status")
            if rr.get("tax_url") or st in ("DONE", "ERROR"):
                if st == "ERROR":
                    raise CheckboxError("Чек відхилено ДПС: %s" % (rr.get("failure_message") or "невідома причина"))
                url = rr.get("tax_url") or rr.get("url") or ""
                fiscal = rr.get("fiscal_code") or fiscal
                break
    # клієнту даємо ФАЙЛ чека (гарна сторінка), а не пошук у кабінеті ДПС
    receipt_url = "https://check.checkbox.ua/%s" % rid if rid else url
    return {
        "id": rid,
        "fiscal_code": fiscal,
        "url": receipt_url,   # check.checkbox.ua — сам чек
        "tax_url": url,       # cabinet.tax.gov.ua — для архіву
        "relation_id": str(d.get("pre_payment_relation_id") or relation_id or ""),
    }
