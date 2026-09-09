"""Daily Orac-only retail sync. Default is a dry run; run state persists outside image."""
import concurrent.futures
import fcntl
import json
import os
import urllib.request
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.warehouse.models import Product
from apps.warehouse.orac_prices import allowed_source, decision, parse_price_page
from apps.warehouse.shop_sync import queue_product_sync


class Command(BaseCommand):
    help = 'Observe approved public Orac retail sources; --apply allows guarded Product.price updates.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--state-dir', default='/app/warehouse_photos/orac-price-sync')

    def handle(self, *args, **options):
        root = Path(options['state_dir']); root.mkdir(parents=True, exist_ok=True)
        lock = (root / 'run.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CommandError('Another Orac price run is active')
        path = root / 'state.json'
        state = json.loads(path.read_text()) if path.exists() else {}
        now = timezone.now(); day = now.date().isoformat()
        products = list(Product.objects.filter(shop_specs__orac__import_version='20260909-v1', is_active=True).order_by('id'))
        if options['limit']:
            products = products[:options['limit']]
        def observe(p):
            cfg = p.shop_specs['orac']['price_sync']; url = cfg.get('source_url', '')
            record = {'id': p.id, 'sku': p.shop_specs['orac']['sku'], 'source_url': url}
            if not allowed_source(url):
                return p, record | {'status': 'held:no_verified_live_source'}
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'Wallcov-Catalog-PriceCheck/1.0'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    if not allowed_source(response.geturl()):
                        raise ValueError('unexpected_source_redirect')
                    text = response.read(2000000).decode('utf-8')
                amount, digest = parse_price_page(text, record['sku'])
                return p, record | {'observed': str(amount), 'source_hash': digest}
            except Exception as exc:
                return p, record | {'status': 'held:source_error', 'error': str(exc)[:200]}
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for p, rec in pool.map(observe, products):
                cfg = p.shop_specs['orac']['price_sync']; prior = state.get(str(p.id), {})
                if 'observed' in rec:
                    applied = prior.get('last_applied', cfg['last_applied'])
                    candidate = prior.get('candidate') if prior.get('candidate_day', day) < day else None
                    status = decision(p.price, applied, rec['observed'], cfg.get('hold') or prior.get('hold', ''), candidate)
                    rec['status'] = status; rec['before'] = str(p.price)
                    if options['apply']:
                        entry = dict(prior, last_checked=now.isoformat(), source_hash=rec['source_hash'], observed=rec['observed'], last_applied=applied)
                        if status.startswith('held:manual'):
                            entry['hold'] = 'manual_price_change'
                        if status == 'pending_second_observation':
                            entry.update(candidate=rec['observed'], candidate_day=day)
                        elif status == 'unchanged':
                            entry.pop('candidate', None); entry.pop('candidate_day', None)
                        if status == 'update':
                            with transaction.atomic():
                                live = Product.objects.select_for_update().get(pk=p.id)
                                live_cfg = live.shop_specs.get('orac', {}).get('price_sync', {})
                                if live.price != p.price or not live.is_active or live_cfg != cfg:
                                    rec['status'] = 'held:concurrent_change'
                                else:
                                    with (root / 'price-journal.jsonl').open('a') as journal:
                                        journal.write(json.dumps(rec | {'checked_at': now.isoformat(), 'phase': 'before_update'}) + '\n')
                                    live.price = Decimal(rec['observed'])
                                    live.save(update_fields=['price', 'updated_at'])
                                    queue_product_sync(live)
                                    entry['last_applied'] = rec['observed']; entry.pop('candidate', None)
                        state[str(p.id)] = entry
                rec['checked_at'] = now.isoformat(); results.append(rec)
        report = {'checked_at': now.isoformat(), 'dry_run': not options['apply'], 'count': len(results), 'results': results}
        name = now.strftime('%Y%m%dT%H%M%S') + ('-apply' if options['apply'] else '-dry')
        (root / (name + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        if options['apply']:
            temp = root / 'state.json.tmp'; temp.write_text(json.dumps(state, ensure_ascii=False, indent=2)); os.replace(temp, path)
        from collections import Counter
        self.stdout.write(json.dumps({'dry_run': not options['apply'], 'count': len(results), 'statuses': dict(Counter(r['status'] for r in results)), 'report': str(root / (name + '.json'))}))
