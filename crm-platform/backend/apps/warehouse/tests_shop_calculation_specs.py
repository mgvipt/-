from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json

from django.test import SimpleTestCase

from .shop_sync import product_calculation_specs, product_payload


class ShopCalculationSpecsTest(SimpleTestCase):
    def product(self, rate=Decimal('0.1500'), unit='кг', specs=None):
        return SimpleNamespace(consumption_per_m2=rate, unit=unit,
                               pack_factor=Decimal('12'), shop_specs=specs or {})

    def test_finished_consumption_keeps_units_without_pack_or_layer_conversion(self):
        p = self.product()
        self.assertEqual(product_calculation_specs(p)['calc'], {
            'consumption_per_m2': '0.1500', 'unit': 'кг',
            'basis': 'finished_m2', 'source': 'crm_product',
        })
        p.unit = 'л'
        self.assertEqual(product_calculation_specs(p)['calc']['unit'], 'л')

    def test_cleared_or_invalid_rate_cannot_leave_a_stale_shop_rate(self):
        for value in (None, Decimal('0'), Decimal('-0.1')):
            with self.subTest(rate=value):
                p = self.product(value, specs={'calc': {'consumption_per_m2': '9', 'unit': 'шт'}})
                self.assertIsNone(product_calculation_specs(p)['calc']['consumption_per_m2'])

    def test_canonical_rate_overrides_json_without_mutating_crm_specs(self):
        old = {'calc': {'consumption_per_m2': '99'}, 'categories': ['decor'],
               'source_columns': {'Цена за кг, грн': '1080'}}
        p = self.product(Decimal('0.2000'), specs=old)
        result = product_calculation_specs(p)
        self.assertEqual(result['calc']['consumption_per_m2'], '0.2000')
        self.assertEqual(result['categories'], ['decor'])
        self.assertEqual(result['price_per_kg'], '1080')
        self.assertEqual(old['calc']['consumption_per_m2'], '99')
        self.assertNotIn('price_per_kg', old)

    def test_payload_publishes_current_rate_and_price_without_saving_duplicates(self):
        p = self.product()
        for key, value in {
            'id': 1610, 'sku': 'TEST-SILK', 'name': 'Silk', 'price': Decimal('1080.00'),
            'currency': 'UAH', 'is_active': True, 'shop_enabled': True, 'is_drop': True,
            'shop_group_key': 'test-silk', 'shop_parent_name': 'Silk', 'shop_slug': 'test-silk',
            'shop_short_description': '', 'shop_full_description': '', 'shop_benefits': [],
            'shop_effect': '', 'shop_rooms': [], 'shop_beginner': False, 'shop_video_url': '',
            'shop_instruction_url': '', 'shop_sort': 0, 'shop_badges': [],
            'shop_variant_type': 'product', 'shop_has_board': None, 'shop_is_tinted': None,
            'shop_variant_order': 1, 'shop_variant_name': '', 'shop_contents': '',
            'seo_title': '', 'seo_description': '', 'seo_h1': '', 'seo_categories': [],
            'seo_faqs': [], 'seo_index': True, 'updated_at': None,
        }.items():
            setattr(p, key, value)
        p.stock = lambda: Decimal(0)
        p.images = Mock()
        p.images.filter.return_value.order_by.return_value = []
        with patch('apps.warehouse.shop_sync.prepare_product_for_shop', return_value=p), \
             patch('apps.warehouse.shop_sync.catalog_validation_errors', return_value=[]), \
             patch('apps.warehouse.shop_sync.effective_category_path', return_value=['Декор']):
            wire = json.loads(json.dumps(product_payload(p)))['product']
        self.assertEqual(wire['price'], '1080.00')
        self.assertEqual(wire['unit'], 'кг')
        self.assertEqual(wire['specs']['calc']['consumption_per_m2'], '0.1500')
        self.assertEqual(p.shop_specs, {})
