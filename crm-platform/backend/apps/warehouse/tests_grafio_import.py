import copy
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from apps.warehouse.models import Product, ProductCategory, ProductImage
from apps.integrations.models import SupplierProductMap


class GrafioImportTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'snapshot.json'
        self.snapshot = {'complete': True, 'checked_at': '2026-09-17T18:00:00Z',
            'products': [{'sourceID': n, 'name': f'Карниз KR {n}', 'slug': f'karnyz-{n}',
                'sourceURL': f'https://www.grafio-decor.com.ua/product/karnyz-{n}',
                'currency': 'UAH', 'unit': 'м.п.', 'category': {'name': 'Карнизи', 'slug': 'karnyzy'},
                'price': '403.00', 'status': 'verified', 'images': ['https://source/image.jpg'],
                'dimensions': '100 × 2000 мм'} for n in range(1, 224)]}
        self.path.write_text(json.dumps(self.snapshot))

    def run_import(self, **kw):
        out = io.StringIO()
        call_command('import_grafio_catalog', str(self.path), stdout=out, **kw)
        return json.loads(out.getvalue())

    def apply(self, backup, **kw):
        with patch.dict(os.environ, {'DRY_RUN': '0'}):
            return self.run_import(apply=True, ids='1,2', backup=str(Path(self.tmp.name)/backup), **kw)

    def test_dry_run_has_no_database_writes(self):
        result = self.run_import()
        self.assertEqual(result['counts'], {'create': 223})
        self.assertFalse(Product.objects.exists())
        self.assertFalse(ProductCategory.objects.exists())
        self.assertFalse(SupplierProductMap.objects.exists())

    def test_pilot_idempotence_preserves_legacy_and_no_approved_images(self):
        legacy = Product.objects.create(name='Grafio Decor KR1', sku='B24-123', unit='шт', price=33)
        self.apply('first.json')
        self.apply('second.json')
        self.assertEqual(Product.objects.count(), 3)
        self.assertEqual(SupplierProductMap.objects.count(), 2)
        legacy.refresh_from_db()
        self.assertEqual(legacy.price, 33)
        p = Product.objects.get(sku='GRAFIO-1')
        self.assertFalse(p.shop_enabled)
        self.assertFalse(p.shop_managed)
        self.assertFalse(p.track_stock)
        self.assertFalse(ProductImage.objects.exists())
        self.assertTrue((Path(self.tmp.name)/'first.json').exists())

    def test_review_required_is_quote_only(self):
        self.snapshot['products'][0]['status'] = 'review_required'
        self.path.write_text(json.dumps(self.snapshot))
        self.apply('quote.json')
        p = Product.objects.get(sku='GRAFIO-1')
        self.assertEqual(p.price, 0)
        self.assertTrue(p.shop_specs['supplier']['quote_only'])

    def test_unit_change_and_identity_conflict_fail_atomic(self):
        self.apply('first.json')
        self.snapshot['products'][1]['unit'] = 'шт.'
        self.path.write_text(json.dumps(self.snapshot))
        with self.assertRaises(CommandError):
            self.apply('bad.json')
        self.assertEqual(Product.objects.count(), 2)
        self.assertFalse((Path(self.tmp.name)/'bad.json').exists())

    def test_incomplete_duplicate_snapshot_and_apply_guard(self):
        with self.assertRaises(CommandError):
            self.run_import(apply=True)
        self.snapshot['products'][1]['sourceID'] = 1
        self.path.write_text(json.dumps(self.snapshot))
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertFalse(Product.objects.exists())

    def test_stale_snapshot_rejected(self):
        self.apply('first.json')
        self.snapshot['checked_at'] = '2026-09-16T18:00:00Z'
        self.path.write_text(json.dumps(self.snapshot))
        with self.assertRaises(CommandError):
            self.apply('stale.json')
        self.assertEqual(Product.objects.get(sku='GRAFIO-1').price, 403)

    def test_pilot_cannot_push_partial_price_catalog(self):
        with self.assertRaises(CommandError):
            self.apply('partial.json', push=True)
        self.assertFalse(Product.objects.exists())

    def test_full_push_sends_quote_null_and_stable_event_id(self):
        from unittest.mock import MagicMock
        self.snapshot['products'][0]['status'] = 'review_required'
        self.path.write_text(json.dumps(self.snapshot))
        response = MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        target = 'apps.warehouse.management.commands.import_grafio_catalog.urllib.request.urlopen'
        with self.settings(SHOP_WEBHOOK_SECRET='isolated-test-secret'), patch(target, return_value=response) as send:
            with patch.dict(os.environ, {'DRY_RUN': '0'}):
                self.run_import(apply=True, all=True, push=True, backup=str(Path(self.tmp.name)/'all1.json'))
                first = json.loads(send.call_args.args[0].data)
                self.run_import(apply=True, all=True, push=True, backup=str(Path(self.tmp.name)/'all2.json'))
                second = json.loads(send.call_args.args[0].data)
        self.assertEqual(first['event_uuid'], second['event_uuid'])
        self.assertEqual(len(first['products']), 223)
        self.assertIsNone(first['products'][0]['price'])
        self.assertEqual(Product.objects.count(), 223)

    def test_price_refresh_preserves_operator_fields_and_images(self):
        self.apply('first.json')
        p = Product.objects.get(sku='GRAFIO-1')
        category = ProductCategory.objects.create(name='Ручна папка')
        p.name = 'Ручна назва'
        p.description = 'Перевірений опис'
        p.category = category
        p.shop_enabled = True
        p.shop_managed = True
        p.shop_specs['supplier']['approved_assets'] = ['photo-123']
        p.save()
        photo = ProductImage.objects.create(product=p, file_path='approved.jpg', is_approved=True)
        self.snapshot['products'][0]['price'] = '444.50'
        self.snapshot['products'][0]['images'] = ['replacement.jpg']
        self.snapshot['checked_at'] = '2026-09-18T18:00:00Z'
        self.path.write_text(json.dumps(self.snapshot))
        self.apply('refresh.json')
        p.refresh_from_db()
        photo.refresh_from_db()
        self.assertEqual(str(p.price), '444.50')
        self.assertEqual(p.name, 'Ручна назва')
        self.assertEqual(p.description, 'Перевірений опис')
        self.assertEqual(p.category_id, category.pk)
        self.assertTrue(p.shop_enabled)
        self.assertTrue(p.shop_managed)
        self.assertEqual(p.shop_specs['supplier']['approved_assets'], ['photo-123'])
        self.assertEqual(p.shop_specs['supplier']['images'], ['https://source/image.jpg'])
        self.assertTrue(photo.is_approved)
        self.assertEqual(photo.file_path, 'approved.jpg')
