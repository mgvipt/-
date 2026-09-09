"""Strict public retail observations. No markup, fallback price or catalogue deletion."""
import hashlib
import html
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse


def parse_price_page(text, expected_sku):
    sku = re.search(r'<b>арт\.:?</b>\s*([^<]+)', text)
    price = re.search(r'prod-column_price.*?<b>Ціна:</b>\s*([\d\s.,]+)\s*грн', text, re.S)
    if not sku or html.unescape(sku[1]).strip() != expected_sku:
        raise ValueError('source_sku_mismatch')
    if not price:
        raise ValueError('source_price_missing')
    try:
        amount = Decimal(re.sub(r'\s+', '', price[1]).replace(',', '.'))
    except InvalidOperation:
        raise ValueError('source_price_invalid')
    if not amount.is_finite() or amount <= 0 or amount > 1000000:
        raise ValueError('source_price_implausible')
    return amount.quantize(Decimal('.01')), hashlib.sha256(text.encode()).hexdigest()


def allowed_source(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.netloc == 'ampir.ua' and p.path.startswith('/product/') and not p.query


def decision(current, applied, observed, hold='', previous_candidate=None, max_change=Decimal('.10')):
    current, applied, observed = map(lambda x: Decimal(str(x)), (current, applied, observed))
    if hold:
        return 'held:' + hold
    if current != applied:
        return 'held:manual_price_change'
    if observed <= 0 or applied <= 0 or observed > 1000000:
        return 'held:invalid_price'
    if observed == current:
        return 'unchanged'
    if abs(observed / applied - 1) > max_change:
        return 'held:abrupt_source_change'
    if previous_candidate is None or Decimal(str(previous_candidate)) != observed:
        return 'pending_second_observation'
    return 'update'
