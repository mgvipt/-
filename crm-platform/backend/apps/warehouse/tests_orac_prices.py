import unittest
from apps.warehouse.orac_prices import allowed_source, decision, parse_price_page


class OracPriceSafetyTests(unittest.TestCase):
    def test_exact_sku_and_positive_price_required(self):
        text = '<b>арт.:</b> SX157 <div class="prod-column_price"><b>Ціна:</b> 480,00 грн'
        self.assertEqual(str(parse_price_page(text, 'SX157')[0]), '480.00')
        for sku, html in [('SX157F', text), ('SX157', text.replace('480,00', '0')), ('SX157', '<html>temporary error</html>')]:
            with self.assertRaises(ValueError): parse_price_page(html, sku)

    def test_manual_override_and_source_conflict_never_overwritten(self):
        self.assertEqual(decision(500,480,490,previous_candidate=490), 'held:manual_price_change')
        self.assertEqual(decision(480,480,490,hold='price_list_website_conflict',previous_candidate=490), 'held:price_list_website_conflict')

    def test_daily_confirmation_and_jump_guard(self):
        self.assertEqual(decision(480,480,490), 'pending_second_observation')
        self.assertEqual(decision(480,480,490,previous_candidate=490), 'update')
        self.assertEqual(decision(480,480,900,previous_candidate=900), 'held:abrupt_source_change')
        self.assertEqual(decision(480,480,480), 'unchanged')

    def test_source_allowlist(self):
        self.assertTrue(allowed_source('https://ampir.ua/product/plintus-40/'))
        for url in ['http://ampir.ua/product/x/','https://ampir.ua.evil.test/product/x/','https://ampir.ua@evil.test/product/x/']:
            self.assertFalse(allowed_source(url))
