"""LiqPay-клієнт CRM: підпис + генерація checkout-посилання + верифікація callback.
Алгоритм LiqPay: data=base64(json(payload)); signature=base64(sha1(private+data+private))."""
import base64, hashlib, hmac, json
from urllib.parse import quote

CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"


def encode_data(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def decode_data(data_b64):
    return json.loads(base64.b64decode(data_b64.encode("ascii")).decode("utf-8"))


def sign(data_b64, private_key):
    raw = (private_key + data_b64 + private_key).encode("utf-8")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")


def verify(data_b64, signature, private_key):
    if not (data_b64 and signature and private_key):
        return False
    return hmac.compare_digest(sign(data_b64, private_key), signature)


def build_checkout_url(public_key, private_key, amount, order_id, description, server_url=None, result_url=None, sandbox=False, paytypes=None):
    payload = {"public_key": public_key, "version": 3, "action": "pay", "amount": float(amount),
               "currency": "UAH", "order_id": order_id, "description": description}
    if server_url:
        payload["server_url"] = server_url
    if result_url:
        payload["result_url"] = result_url
    if sandbox:
        payload["sandbox"] = 1
    if paytypes:
        payload["paytypes"] = paytypes  # обмежити способи оплати (card / paypart...)
    data = encode_data(payload)
    sig = sign(data, private_key)
    return "%s?data=%s&signature=%s" % (CHECKOUT_URL, quote(data, safe=""), quote(sig, safe=""))
