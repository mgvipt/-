"""Import reviewed supplier snapshot. Dry run is default; no network or client messages."""
import hashlib
import hmac
import time
import uuid
import urllib.request
import json
import os
from urllib.parse import unquote
from django.utils.html import strip_tags
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils.dateparse import parse_datetime
from apps.warehouse.models import Product, ProductCategory
from apps.integrations.models import SupplierProductMap

SUPPLIER = 'grafio-catalog-source-id'
ROOT = 'Фасадний декор Grafio'


def validated_rows(snapshot):
    if snapshot.get('complete') is not True:
        raise CommandError('Incomplete supplier snapshot')
    checked = snapshot.get('completedAt') or snapshot.get('checked_at')
    if not checked or not parse_datetime(checked) or parse_datetime(checked).tzinfo is None:
        raise CommandError('Snapshot requires ISO timestamp with timezone')
    rows = snapshot.get('products', [])
    if len(rows) != 223:
        raise CommandError('Expected complete 223-product snapshot')
    seen = set()
    for row in rows:
        sid = str(row['sourceID'])
        if not sid.isdigit() or sid in seen:
            raise CommandError('Duplicate/invalid sourceID')
        seen.add(sid)
        for field in ('name', 'slug', 'sourceURL', 'unit', 'category'):
            if not row.get(field):
                raise CommandError(f'{sid}: missing {field}')
        if row.get('currency') != 'UAH' or len(row['unit']) > 16:
            raise CommandError(f'{sid}: invalid currency/unit')
        if not isinstance(row['category'], dict) or not row['category'].get('name'):
            raise CommandError(f'{sid}: invalid category')
        if row.get('status') not in {'verified', 'review_required', 'price_on_request'}:
            raise CommandError(f'{sid}: unknown review status')
        if not row['sourceURL'].startswith('https://www.grafio-decor.com.ua/product/'):
            raise CommandError(f'{sid}: unexpected source URL')
        price = row.get('price')
        if price is not None:
            try:
                value = Decimal(str(price))
                if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -2:
                    raise InvalidOperation()
            except InvalidOperation:
                raise CommandError(f'{sid}: invalid supplier price')
    return rows


def fields(row, checked):
    sid = str(row['sourceID'])
    usable = row.get('status') == 'verified' and row.get('price') is not None
    # Source images remain references, never approved ProductImage entries.
    source = {k: row.get(k) for k in ('sourceID', 'sourceURL', 'price', 'unit', 'status',
              'reviewIssues', 'dimensions', 'attributes', 'images', 'drawings',
              'sourcePriceSSR', 'sourceDiscrepancies', 'visiblePriceQuote', 'priceField')}
    source.update(key='grafio', checked_at=checked, quote_only=not usable)
    dimensions = row.get('dimensions') or ''
    if not isinstance(dimensions, str):
        dimensions = json.dumps(dimensions, ensure_ascii=False)
    description = row['name'] + (f'\nРозміри: {dimensions}' if dimensions else '')
    for edge in row.get('attributes') or []:
        node = edge.get('node') or {}
        label = strip_tags(node.get('label') or '')
        terms = [e.get('node', {}).get('name') for e in node.get('terms', {}).get('edges', [])]
        values = [strip_tags(v) for v in terms if v]
        if not values:
            values = [strip_tags(unquote(v).replace('-', ' ')) for v in node.get('options', []) if v]
        if label and values and label != 'Розмір':
            description += '\n' + label + ': ' + ', '.join(values)

    return dict(name=row['name'], sku=f'GRAFIO-{sid}', unit=row['unit'],
                price=Decimal(str(row['price'])) if usable else Decimal('0'),
                currency='UAH', description=description,
                shop_short_description=description, shop_specs={'supplier': source},
                shop_enabled=False, shop_managed=False, shop_status='draft',
                shop_group_key=f'facade-{sid}', shop_slug=row['slug'],
                shop_parent_name=row['name'], seo_index=False)


class Command(BaseCommand):
    help = 'Dry-run Grafio import; --apply requires --backup and explicit selected IDs or --all.'

    def add_arguments(self, parser):
        parser.add_argument('snapshot')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--all', action='store_true')
        parser.add_argument('--ids', default='')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--backup')
        parser.add_argument('--push', action='store_true')

    def handle(self, *args, **opts):
        raw = Path(opts['snapshot']).read_bytes()
        snapshot = json.loads(raw)
        allrows = validated_rows(snapshot)
        ids = {s.strip() for s in opts['ids'].split(',') if s.strip()}
        if ids - {str(r['sourceID']) for r in allrows}:
            raise CommandError('Unknown requested sourceID')
        rows = [r for r in allrows if not ids or str(r['sourceID']) in ids]
        if opts['limit'] is not None:
            if opts['limit'] < 1:
                raise CommandError('limit must be positive')
            rows = rows[:opts['limit']]
        if opts['push'] and (ids or opts['limit']):
            raise CommandError('Push requires full catalog, never a pilot')
        apply = opts['apply'] and os.environ.get('DRY_RUN', '1') == '0'
        if opts['push'] and not apply:
            raise CommandError('Push requires explicit apply')
        if opts['apply'] and not apply:
            raise CommandError('Set DRY_RUN=0 explicitly to apply')
        if apply and (not opts['backup'] or (not ids and not opts['all'])):
            raise CommandError('Apply requires backup and --ids or --all')
        plan = []
        with transaction.atomic():
            # One importer at a time, including first import where no mapping row exists.
            if apply and connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', [954223])
            for row in rows:
                sid = str(row['sourceID'])
                mapping = SupplierProductMap.objects.filter(supplier_key=SUPPLIER, their_name=sid).first()
                candidates = list(Product.objects.filter(sku=f'GRAFIO-{sid}'))
                if len(candidates) > 1 or (mapping and candidates and mapping.product_id != candidates[0].pk):
                    raise CommandError(f'{sid}: identity conflict')
                product = mapping.product if mapping else (candidates[0] if candidates else None)
                if product and (product.shop_specs or {}).get('supplier', {}).get('sourceID') != row['sourceID']:
                    raise CommandError(f'{sid}: existing SKU lacks exact source identity')
                if product and product.unit != row['unit']:
                    raise CommandError(f'{sid}: unit changed; manual review required')
                if product:
                    previous = product.shop_specs['supplier'].get('checked_at')
                    current = snapshot.get('completedAt') or snapshot.get('checked_at')
                    if previous and parse_datetime(previous) > parse_datetime(current):
                        raise CommandError(f'{sid}: snapshot is older than imported price')
                plan.append((row, product, fields(row, snapshot.get('completedAt') or snapshot.get('checked_at') or snapshot.get('date'))))
            if apply:
                existing = [p for _, p, _ in plan if p]
                backup = {'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
                          'products': json.loads(serializers.serialize('json', existing)),
                          'maps': json.loads(serializers.serialize('json', SupplierProductMap.objects.filter(supplier_key=SUPPLIER))),
                          'categories': json.loads(serializers.serialize('json', ProductCategory.objects.all())),
                          'planned_source_ids': [str(r['sourceID']) for r, _, _ in plan]}
                with open(opts['backup'], 'x', encoding='utf-8') as output:
                    os.chmod(opts['backup'], 0o600)
                    json.dump(backup, output, ensure_ascii=False)
                root, _ = ProductCategory.objects.get_or_create(name=ROOT, parent=None)
                for row, product, data in plan:
                    if product:
                        # Recurring sync owns price provenance only. Manual descriptions,
                        # category, publication flags and approved image metadata are untouched.
                        previous_specs = dict(product.shop_specs or {})
                        previous_source = dict(previous_specs.get('supplier') or {})
                        incoming = data['shop_specs']['supplier']
                        for key in ('price', 'checked_at', 'status', 'reviewIssues', 'sourceURL', 'quote_only',
                                    'sourcePriceSSR', 'sourceDiscrepancies', 'visiblePriceQuote', 'priceField'):
                            previous_source[key] = incoming.get(key)
                        previous_specs['supplier'] = previous_source
                        product.price = data['price']
                        product.currency = data['currency']
                        product.shop_specs = previous_specs
                        product.save(update_fields=['price', 'currency', 'shop_specs', 'updated_at'])
                    else:
                        category, _ = ProductCategory.objects.get_or_create(parent=root, name=row['category']['name'])
                        product = Product.objects.create(**data, category=category, track_stock=False, is_drop=False)
                    SupplierProductMap.objects.get_or_create(supplier_key=SUPPLIER,
                        their_name=str(row['sourceID']), defaults={'product': product, 'qty_factor': 1})
            result = {'dry_run': not apply, 'selected': len(plan),
                      'counts': dict(Counter('update' if p else 'create' for _, p, _ in plan)),
                      'quote_only': sum(d['shop_specs']['supplier']['quote_only'] for _, _, d in plan),
                      'rows': [{'source_id': r['sourceID'], 'product_id': p.pk if p else None,
                                'sku': d['sku'], 'price': str(d['price']), 'unit': d['unit'],
                                'category': r['category']['name']} for r, p, d in plan]}
        # DB is committed before network I/O. Same snapshot yields same event UUID;
        # rerunning after a network failure updates the same 223 records and retries safely.
        if opts['push']:
            checked = snapshot.get('completedAt') or snapshot.get('checked_at')
            if not checked or not settings.SHOP_WEBHOOK_SECRET:
                raise CommandError('DB imported; push missing timestamp or SHOP_WEBHOOK_SECRET')
            exported = []
            for row in allrows:
                product = SupplierProductMap.objects.get(supplier_key=SUPPLIER, their_name=str(row['sourceID'])).product
                quote = product.shop_specs['supplier']['quote_only']
                exported.append(dict(source_id=row['sourceID'], crm_product_id=product.pk,
                    price=None if quote else str(product.price), currency=product.currency,
                    unit=product.unit, source_url=row['sourceURL']))
            envelope = dict(event_uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'grafio:'+hashlib.sha256(raw).hexdigest())),
                            checked_at=checked, complete=True, products=exported)
            body = json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode()
            stamp = str(int(time.time()))
            signature = hmac.new(settings.SHOP_WEBHOOK_SECRET.encode(), stamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
            request = urllib.request.Request('https://wallcov.com.ua/api/crm/facade-catalog', data=body,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                         'X-Wallcov-Timestamp': stamp, 'X-Wallcov-Signature': signature}, method='POST')
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    if response.status != 200:
                        raise CommandError('DB imported; shop did not acknowledge snapshot')
                    result['shop_push'] = json.loads(response.read())
            except Exception as exc:
                raise CommandError('DB imported; shop push failed; retry identical snapshot with a new backup path') from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
