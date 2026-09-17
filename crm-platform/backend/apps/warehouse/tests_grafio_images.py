import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from apps.warehouse.models import Product, ProductImage
from apps.integrations.models import SupplierProductMap


class GrafioImageImportTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'manifest.json'
        self.asset = self.root / 'reviewed.png'
        Image.new('RGB', (8, 8), 'white').save(self.asset)
        self.row = {'sourceid': 954, 'kind': 'photo', 'local_path': str(self.asset),
                    'sha256': hashlib.sha256(self.asset.read_bytes()).hexdigest(),
                    'review': 'PASS', 'logo_detected': False, 'source_url': 'https://source/kr101.png'}
        self.path.write_text(json.dumps({'assets': [self.row]}))
        self.p = Product.objects.create(name='Карниз KR101', sku='GRAFIO-954', shop_specs={'supplier': {'sourceID': 954}})
        SupplierProductMap.objects.create(supplier_key='grafio-catalog-source-id', their_name='954', product=self.p)

    def run_import(self, **kw):
        out = io.StringIO()
        with self.settings(WAREHOUSE_PHOTOS_DIR=str(self.root/'storage')):
            call_command('import_grafio_images', str(self.path), stdout=out, **kw)
        return json.loads(out.getvalue())

    def apply(self, backup):
        with patch.dict(os.environ, {'DRY_RUN': '0'}):
            return self.run_import(apply=True, ids='954', backup=str(self.root/backup))

    def test_dry_run_no_image_or_file_writes(self):
        self.assertEqual(self.run_import()['create'], 1)
        self.assertFalse(ProductImage.objects.exists())
        self.assertFalse((self.root/'storage').exists())

    def test_idempotent_import_preserves_existing_image(self):
        old = ProductImage.objects.create(product=self.p, file_path='manual.jpg', is_primary=True, is_approved=False)
        self.apply('first.json')
        self.assertEqual(self.apply('second.json')['existing'], 1)
        self.assertEqual(ProductImage.objects.count(), 2)
        old.refresh_from_db()
        self.assertTrue(old.is_primary)
        self.assertFalse(old.is_approved)
        imported = ProductImage.objects.exclude(pk=old.pk).get()
        self.assertTrue(imported.is_approved)
        self.assertFalse(imported.is_primary)
        self.assertEqual(Path(imported.file_path).read_bytes(), self.asset.read_bytes())

    def test_unknown_watermark_and_tampered_bytes_rejected(self):
        for change in ({'review': 'UNKNOWN'}, {'logo_detected': True}, {'sha256': '0'*64}):
            self.path.write_text(json.dumps({'assets': [{**self.row, **change}]}))
            with self.assertRaises(CommandError):
                self.apply('bad.json')
        self.assertFalse(ProductImage.objects.exists())
        self.assertFalse((self.root/'bad.json').exists())

    def test_missing_exact_source_mapping_rejected(self):
        self.row['sourceid'] = 999
        self.path.write_text(json.dumps({'assets': [self.row]}))
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertFalse(ProductImage.objects.exists())
