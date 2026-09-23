"""DSV package yield needs mass ratio and both densities, independently of price."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from apps.content_library import topciment

class DsvYieldTests(SimpleTestCase):
    def calculate(self, density_b=None, price='10'):
        mixing = {'a_to_b_mass': '2', 'density_a_kg_l': '1', 'b_pack_count': 1}
        if density_b is not None:
            mixing['density_b_kg_l'] = density_b
        def product(key, pack):
            return SimpleNamespace(id=1 if key=='dsv-a' else 2, name=key,
                shop_specs={'topciment_key': key, 'mixing': mixing,
                            'calculator_rates': {'microfino-dsv': '0.2'}},
                pack_factor=Decimal(pack), unit='л', price=Decimal(price), currency='UAH',
                updated_at=datetime(2026, 9, 23))
        with patch.object(topciment, 'catalog', return_value={
                'dsv-a': product('dsv-a', '4'), 'dsv-b': product('dsv-b', '1')}):
            result=topciment.calculate('microfino-dsv', 20, 0)
        return next(row for row in result['rows'] if row['key']=='dsv-kit'), result

    def test_missing_b_density_retains_need_without_packages_or_total(self):
        row, result=self.calculate()
        self.assertEqual(row['quantity'], 4)
        for field in ('pack', 'packs', 'purchase_quantity', 'pack_price', 'subtotal'):
            self.assertIsNone(row[field], field)
        self.assertTrue(any('Topsealer DSV: потребу' in note for note in result['notes']))

    def test_known_densities_use_limiting_component(self):
        # One litre B limits the 2:1 mass blend to 2 L A + 1 L B, not nominal 5 L.
        row, result=self.calculate('1')
        self.assertEqual(row['quantity'], 4)
        self.assertEqual(row['pack'], 3)
        self.assertEqual(row['packs'], 2)
        self.assertEqual(row['purchase_quantity'], 6)
        self.assertEqual(row['pack_price'], 50)
        self.assertEqual(row['subtotal'], 100)
        self.assertFalse(any('Topsealer DSV: потребу' in note for note in result['notes']))

    def test_unknown_price_does_not_hide_known_physical_yield(self):
        row, result=self.calculate('1', '0')
        self.assertEqual(row['pack'], 3)
        self.assertEqual(row['packs'], 2)
        self.assertEqual(row['quantity'], 4)
        self.assertIsNone(row['pack_price'])
        self.assertIsNone(row['subtotal'])
        self.assertIn(row['name'], result['missing'])

    def test_system_review_blocks_complete_with_verified_facts_and_prices(self):
        owner=SimpleNamespace(id=10, name='Verified material', unit='кг', price=Decimal('5'),
            currency='UAH', pack_factor=Decimal('10'), updated_at=datetime(2026,9,23),
            shop_specs={'topciment_key':'grip', 'calculator_rates':{'efectto-wall':'0.3'},
                'technical_facts':{'technical_review':{'required':False}},
                'calculator_system_review':{'efectto-wall':{'required':True}}})
        with patch.object(topciment,'catalog',return_value={'grip':owner}), patch.object(
                topciment,'SYSTEMS',[{'id':'efectto-wall','name':'Mixed system','materials':['grip']}]):
            guarded=topciment.calculate('efectto-wall',10,0)
            self.assertEqual(guarded['missing'],[])
            self.assertGreater(guarded['known_total'],0)
            self.assertFalse(guarded['complete'])
            self.assertTrue(guarded['rows'][0]['needs_review'])
            self.assertEqual(len(guarded['technical_unverified']),1)
            for malformed in (None, [], 'bad', {'efectto-wall':'bad'}, {'efectto-wall':{'required':'true'}}, {'other':{'required':True}}):
                owner.shop_specs['calculator_system_review']=malformed
                self.assertTrue(topciment.calculate('efectto-wall',10,0)['complete'])
