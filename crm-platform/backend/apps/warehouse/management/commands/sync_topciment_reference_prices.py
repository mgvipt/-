"""Refresh only canonical TOPCIMENT reference prices. Never alter retail prices."""
import concurrent.futures
import fcntl
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.warehouse.models import Product
from apps.warehouse.topciment_prices import (
    allowed_source, fetch, nbu_rate, parse_price_page, refreshed_reference,
)


class Command(BaseCommand):
    help = 'Daily official TOPCIMENT EUR prices and NBU conversion; default dry-run.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--ids', nargs='+', type=int)
        parser.add_argument('--state-dir', default='/app/warehouse_photos/private_topciment_price_sync')

    def handle(self, *args, **options):
        root = Path(options['state_dir'])
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        lock = (root / 'run.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CommandError('Another TOPCIMENT price check is active')
        now = timezone.now()
        day = datetime.now(ZoneInfo('Europe/Kyiv')).date()
        url = ('https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange'
               f'?valcode=EUR&date={day:%Y%m%d}&json')
        try:
            fx = nbu_rate(fetch(url, lambda value: value == url), day)
        except Exception as exc:
            raise CommandError(f'NBU unavailable; prices preserved: {type(exc).__name__}: {exc}')
        query = Product.objects.filter(sku__startswith='TC-20260922-', is_active=True).order_by('id')
        if options['ids']:
            query = query.filter(pk__in=options['ids'])
        products = list(query)

        def observe(product):
            reference = product.shop_specs.get('reference_price') or {}
            rec = {'id': product.pk, 'sku': reference.get('manufacturer_sku'), 'status': 'held:no_exact_source'}
            source = reference.get('url', '')
            if not allowed_source(source) or not reference.get('manufacturer_sku'):
                return product, rec, None
            try:
                amount, availability, digest = parse_price_page(fetch(source, allowed_source), reference['manufacturer_sku'])
                after = refreshed_reference(reference, amount, fx, day, product.pack_factor, availability)
                rec.update(status='unchanged' if after == reference else 'update', source_url=source,
                           source_hash=digest, eur_pack=str(amount), eur_uah=str(fx), uah_pack=after['uah_pack'])
                return product, rec, after
            except Exception as exc:
                rec.update(status='held:source_error', error=f'{type(exc).__name__}: {exc}'[:250])
                return product, rec, None

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for product, rec, after in pool.map(observe, products):
                if options['apply'] and rec['status'] == 'update':
                    with transaction.atomic():
                        live = Product.objects.select_for_update().get(pk=product.pk)
                        if (not live.is_active or live.sku != product.sku or live.unit != product.unit
                                or live.pack_factor != product.pack_factor
                                or live.shop_specs.get('reference_price') != product.shop_specs.get('reference_price')):
                            rec['status'] = 'held:concurrent_change'
                        else:
                            # Price change journal; unchanged daily observations only refresh last-apply.json.
                            entry = {'checked_at': now.isoformat(), 'id': live.pk,
                                     'before': live.shop_specs.get('reference_price'), 'after': after}
                            previous = live.shop_specs.get('reference_price') or {}
                            if any(previous.get(key) != after.get(key) for key in ('eur_pack', 'eur_uah', 'uah_pack', 'url', 'manufacturer_sku')):
                                with (root / 'changes.jsonl').open('a') as journal:
                                    os.chmod(journal.name, 0o600)
                                    journal.write(json.dumps(entry, ensure_ascii=False) + '\n')
                            live.shop_specs = dict(live.shop_specs, reference_price=after)
                            live.save(update_fields=['shop_specs', 'updated_at'])
                            rec['status'] = 'updated'
                results.append(rec)
        report = {'checked_at': now.isoformat(), 'dry_run': not options['apply'], 'nbu_url': url,
                  'eur_uah': str(fx), 'count': len(results),
                  'statuses': dict(Counter(row['status'] for row in results)), 'results': results}
        target = root / ('last-apply.json' if options['apply'] else 'last-dry-run.json')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        self.stdout.write(json.dumps({key: value for key, value in report.items() if key != 'results'}))
        failures = [row for row in results if row['status'] in ('held:source_error', 'held:concurrent_change')]
        if failures:
            raise CommandError(f'{len(failures)} source checks failed; previous prices preserved. Report: {target}')
