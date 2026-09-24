"""Strict, deterministic official-shop price and NBU readers; no AI calls."""
import hashlib
import json
import re
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit


def positive(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('invalid_number')
    if not amount.is_finite() or amount <= 0:
        raise ValueError('non_positive_number')
    return amount


def allowed_source(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'topciment.shop'
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and re.fullmatch(r'/(?:en/)?products/[a-z0-9-]+', parsed.path) is not None
                and not parsed.query and not parsed.fragment)
    except (ValueError, TypeError, AttributeError):
        return False


def fetch(url, allowed):
    if not allowed(url):
        raise ValueError('source_not_allowed')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not allowed(newurl):
                raise ValueError('redirect_not_allowed')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={'User-Agent': 'Wallcov-PriceCheck/1.0'})
    with urllib.request.build_opener(Redirect()).open(request, timeout=30) as response:
        if not allowed(response.geturl()):
            raise ValueError('response_not_allowed')
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('response_too_large')
        return body.decode('utf-8')


def parse_price_page(html, expected_sku):
    if not expected_sku:
        raise ValueError('missing_verified_sku')
    products = []
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        def visit(node):
            if isinstance(node, list):
                for child in node: visit(child)
            elif isinstance(node, dict):
                if node.get('@type') == 'Product': products.append(node)
                if '@graph' in node: visit(node['@graph'])
        visit(doc)
    matched = []
    for product in products:
        offers = product.get('offers') or []
        for offer in offers if isinstance(offers, list) else [offers]:
            if str(offer.get('sku', product.get('sku', ''))) != str(expected_sku):
                continue
            if offer.get('priceCurrency') != 'EUR':
                raise ValueError('currency_not_eur')
            matched.append((positive(offer.get('price')), str(offer.get('availability', ''))))
    if len(matched) != 1:
        raise ValueError('exact_sku_offer_not_unique')
    amount, availability = matched[0]
    return amount, availability, hashlib.sha256(html.encode()).hexdigest()


def nbu_rate(payload, day):
    records = json.loads(payload)
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError('nbu_record_count')
    rec = records[0]
    if rec.get('cc') != 'EUR' or str(rec.get('r030')) != '978':
        raise ValueError('nbu_currency')
    if datetime.strptime(rec.get('exchangedate', ''), '%d.%m.%Y').date() != day:
        raise ValueError('nbu_wrong_date')
    return positive(rec.get('rate'))


def refreshed_reference(reference, amount, fx, day, pack, availability):
    amount, fx, pack = positive(amount), positive(fx), positive(pack)
    uah = (amount * fx).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return dict(reference, date=day.isoformat(), fx_date=day.isoformat(),
                eur_pack=float(amount), eur_uah=float(fx), uah_pack=float(uah),
                uah_unit=float((uah / pack).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)),
                availability=availability, refresh_method='daily_official_shop_nbu')
