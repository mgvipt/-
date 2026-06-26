"""Адаптеры внешних сервисов. Работают, как только в «Интеграциях» заданы ключи."""
import base64
import hashlib
import json
import urllib.request


def _settings(provider):
    from .models import IntegrationSettings
    obj = IntegrationSettings.objects.filter(provider=provider).first()
    if not obj or not obj.is_active:
        raise RuntimeError(f"Интеграция «{provider}» не настроена/не включена")
    return obj.config or {}


# ---------------- LiqPay ----------------
def liqpay_checkout_link(amount, order_id, description) -> str:
    """Готовая ссылка на оплату LiqPay (data+signature по их схеме)."""
    cfg = _settings("liqpay")
    public, private = cfg.get("public_key"), cfg.get("private_key")
    if not (public and private):
        raise RuntimeError("Не заданы public_key/private_key LiqPay")
    params = {
        "version": 3, "public_key": public, "action": "pay",
        "amount": str(amount), "currency": cfg.get("currency", "UAH"),
        "description": description, "order_id": str(order_id),
    }
    data = base64.b64encode(json.dumps(params).encode()).decode()
    sign = base64.b64encode(
        hashlib.sha1((private + data + private).encode()).digest()
    ).decode()
    return f"https://www.liqpay.ua/api/3/checkout?data={data}&signature={sign}"


# ---------------- Nova Poshta ----------------
def _np_call(model, method, props) -> dict:
    cfg = _settings("novaposhta")
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("Не задан api_key Новой Почты")
    payload = json.dumps({
        "apiKey": api_key, "modelName": model,
        "calledMethod": method, "methodProperties": props,
    }).encode()
    req = urllib.request.Request("https://api.novaposhta.ua/v2.0/json/",
                                 data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.loads(r.read().decode())


def np_track(ttn: str) -> dict:
    """Статус посылки по номеру ТТН."""
    return _np_call("TrackingDocument", "getStatusDocuments",
                    {"Documents": [{"DocumentNumber": ttn}]})


def np_create_ttn(props: dict) -> dict:
    """Создать экспресс-накладную (ТТН). props — параметры отправления."""
    return _np_call("InternetDocument", "save", props)


# ---------------- Checkbox (фискализация) ----------------
def checkbox_create_receipt(items: list) -> dict:
    cfg = _settings("checkbox")
    token = cfg.get("token")
    if not token:
        raise RuntimeError("Не задан token Checkbox")
    payload = json.dumps({"goods": items}).encode()
    req = urllib.request.Request(
        "https://api.checkbox.ua/api/v1/receipts/sell",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.loads(r.read().decode())

def np_search_cities(q, limit=20):
    """Address.searchSettlements — автокомпліт міст. Повертає settlement_ref + назву/область/регіон."""
    if not q or len(q) < 2:
        return []
    d = _np_call("Address", "searchSettlements", {"CityName": q, "Limit": str(limit), "Page": "1"})
    out = []
    for row in (d.get("data") or []):
        for a in (row.get("Addresses") or []):
            out.append({
                "settlement_ref": a.get("DeliveryCity") or a.get("Ref"),
                "name": a.get("MainDescription") or "",
                "area": a.get("Area") or "",
                "region": a.get("Region") or "",
                "present": a.get("Present") or "",
            })
    return out


def np_warehouses(ref, q="", limit=60):
    """Address.getWarehouses — відділення/поштомати. Для міст працює CityRef,
    для сіл/смт — SettlementRef. Пробуємо обидва (CityRef першим)."""
    for key in ("CityRef", "SettlementRef"):
        props = {key: ref, "Limit": str(limit), "Page": "1"}
        if q:
            props["FindByString"] = q
        try:
            rows = _np_call("Address", "getWarehouses", props).get("data") or []
        except Exception:
            rows = []
        if rows:
            return [{
                "ref": w.get("Ref"),
                "number": w.get("Number"),
                "desc": w.get("Description") or "",
                "type": w.get("TypeOfWarehouse") or "",
                "max_weight": w.get("TotalMaxWeightAllowed") or "",
            } for w in rows]
    return []

def np_resolve_sender():
    """Резолв відправника (counterparty/contact/phone) один раз — кеш у config інтеграції."""
    cfg = _settings("novaposhta")
    if cfg.get("counterparty_ref") and cfg.get("contact_ref"):
        return cfg
    cp = _np_call("Counterparty", "getCounterparties", {"CounterpartyProperty": "Sender", "Page": "1"})
    rows = cp.get("data") or []
    if not rows:
        raise RuntimeError("NP: у кабінеті немає відправника (Sender)")
    counterparty_ref = rows[0].get("Ref")
    contacts = _np_call("Counterparty", "getCounterpartyContactPersons", {"Ref": counterparty_ref, "Page": "1"})
    crows = contacts.get("data") or []
    contact_ref = crows[0].get("Ref") if crows else ""
    phone = (crows[0].get("Phones") if crows else "") or ""
    from .models import IntegrationSettings
    obj = IntegrationSettings.objects.get(provider="novaposhta")
    obj.config = {**(obj.config or {}), "counterparty_ref": counterparty_ref, "contact_ref": contact_ref, "sender_phone": phone}
    obj.save(update_fields=["config"])
    return obj.config
