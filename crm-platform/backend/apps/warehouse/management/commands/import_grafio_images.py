"""Attach reviewed local image bytes; never fetch or approve unreviewed supplier media."""
import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image
from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from apps.warehouse.models import Product, ProductImage
from apps.integrations.models import SupplierProductMap

SUPPLIER = 'grafio-catalog-source-id'


def reviewed_asset(asset, base):
    if asset.get('review') != 'PASS' or asset.get('logo_detected') is not False:
        raise CommandError('Every selected asset must have visual PASS and logo_detected=false')
    if not str(asset.get('source_url') or '').startswith('https://'):
        raise CommandError('Missing original source URL')
    sid = str(asset.get('sourceid', ''))
    if not sid.isdigit() or asset.get('kind') not in ('photo', 'drawing', 'gallery'):
        raise CommandError('Invalid source identity or image kind')
    path = Path(asset.get('local_path') or '')
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        raise CommandError(f'{sid}: reviewed local bytes unavailable')
    if path.stat().st_size > 10 * 1024 * 1024:
        raise CommandError(f'{sid}: image exceeds 10 MB')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != asset.get('sha256'):
        raise CommandError(f'{sid}: bytes differ from reviewed SHA256')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            fmt = image.format
            if fmt not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 24_000_000:
                raise ValueError('Unsupported image format/dimensions')
            image.verify()
    except Exception as exc:
        raise CommandError(f'{sid}: invalid image bytes') from exc
    return sid, raw, digest, {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}[fmt]


class Command(BaseCommand):
    help = 'Dry-run image manifest; --apply requires DRY_RUN=0, backup and explicit scope.'

    def add_arguments(self, parser):
        parser.add_argument('manifest')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--all', action='store_true')
        parser.add_argument('--ids', default='')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--backup')

    def handle(self, *args, **opts):
        manifest_path = Path(opts['manifest'])
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        assets = manifest.get('assets', [])
        ids = {x.strip() for x in opts['ids'].split(',') if x.strip()}
        if ids - {str(a.get('sourceid')) for a in assets}:
            raise CommandError('Requested sourceID absent from manifest')
        selected = [a for a in assets if not ids or str(a.get('sourceid')) in ids]
        if opts['limit'] is not None:
            if opts['limit'] < 1:
                raise CommandError('limit must be positive')
            selected = selected[:opts['limit']]
        if not selected:
            raise CommandError('No selected assets')
        apply = opts['apply'] and os.environ.get('DRY_RUN', '1') == '0'
        if opts['apply'] and not apply:
            raise CommandError('Explicit DRY_RUN=0 required')
        if apply and (not opts['backup'] or (not ids and not opts['all'])):
            raise CommandError('Apply requires backup and --ids or --all')
        plan, seen = [], set()
        folder = Path(getattr(settings, 'WAREHOUSE_PHOTOS_DIR', '/app/warehouse_photos')) / 'products' / 'grafio'
        with transaction.atomic():
            if apply and connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', [954223])
            for asset in selected:
                sid, raw, digest, ext = reviewed_asset(asset, manifest_path.parent)
                if (sid, digest) in seen:
                    continue
                seen.add((sid, digest))
                mapping = SupplierProductMap.objects.filter(supplier_key=SUPPLIER, their_name=sid).first()
                if not mapping or mapping.product.sku != f'GRAFIO-{sid}':
                    raise CommandError(f'{sid}: exact catalog mapping missing')
                product = Product.objects.select_for_update().get(pk=mapping.product_id) if apply else mapping.product
                source = (product.shop_specs or {}).get('supplier') or {}
                if str(source.get('sourceID')) != sid:
                    raise CommandError(f'{sid}: source identity mismatch')
                existing_assets = source.get('assets') or []
                for existing in existing_assets:
                    if existing.get('source_url') == asset.get('source_url') and existing.get('sha256') != digest:
                        raise CommandError(f'{sid}: same source URL changed bytes; review replacement separately')
                dest = folder / f'{sid}_{digest}{ext}'
                if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
                    raise CommandError(f'{sid}: existing destination hash mismatch')
                image = ProductImage.objects.filter(product=product, file_path=str(dest)).first()
                plan.append((asset, product, image, raw, digest, dest))
            if apply:
                products = {p.pk: p for _, p, _, _, _, _ in plan}
                backup = {'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                          'products': json.loads(serializers.serialize('json', products.values())),
                          'images': json.loads(serializers.serialize('json', ProductImage.objects.filter(product_id__in=products))),
                          'planned_paths': [str(dest) for _, _, _, _, _, dest in plan]}
                with open(opts['backup'], 'x', encoding='utf-8') as output:
                    os.chmod(opts['backup'], 0o600)
                    json.dump(backup, output, ensure_ascii=False)
                folder.mkdir(parents=True, exist_ok=True)
                for asset, original, image, raw, digest, dest in plan:
                    product = Product.objects.get(pk=original.pk)
                    if not dest.exists():
                        # Content-addressed path; do not overwrite any existing bytes.
                        with open(dest, 'xb') as output:
                            output.write(raw)
                    if not image:
                        primary = asset['kind'] == 'photo' and not product.images.filter(is_primary=True).exists()
                        image = ProductImage.objects.create(product=product, file_path=str(dest),
                            order=product.images.count(), alt_text=product.name[:255],
                            is_primary=primary, is_approved=True)
                    specs = dict(product.shop_specs or {})
                    source = dict(specs.get('supplier') or {})
                    stored = list(source.get('assets') or [])
                    if not any(a.get('sha256') == digest for a in stored):
                        stored.append({'sha256': digest, 'source_url': asset.get('source_url'),
                            'kind': asset['kind'], 'review': 'PASS', 'image_id': image.pk})
                    source['assets'] = stored
                    specs['supplier'] = source
                    product.shop_specs = specs
                    product.save(update_fields=['shop_specs', 'updated_at'])
        self.stdout.write(json.dumps({'dry_run': not apply, 'selected': len(plan),
            'create': sum(image is None for _, _, image, _, _, _ in plan),
            'existing': sum(image is not None for _, _, image, _, _, _ in plan),
            'product_ids': sorted({p.pk for _, p, _, _, _, _ in plan})}))
