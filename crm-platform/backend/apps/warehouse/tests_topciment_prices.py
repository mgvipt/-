"""Pure price-contract tests: no network or production database."""
import copy
import io
import json
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from apps.warehouse.topciment_prices import (
    allowed_source, fetch, nbu_rate, parse_price_page, positive, refreshed_reference,
)

DAY = date(2026, 9, 24)
URL = 'https://topciment.shop/en/products/acricem-25l'


def page(sku='TT01010', price='219.60', currency='EUR', **extra):
    offer = dict(sku=sku, price=price, priceCurrency=currency,
                 availability='https://schema.org/InStock', **extra)
    return '<script type="application/ld+json">' + json.dumps({
        '@graph': [{'@type': 'Product', 'offers': [offer]}]}) + '</script>'


class TopcimentPriceTests(TestCase):
    def test_exact_sku_eur_offer_and_digest(self):
        amount, availability, digest = parse_price_page(page(), 'TT01010')
        self.assertEqual(amount, Decimal('219.60'))
        self.assertEqual(availability, 'https://schema.org/InStock')
        self.assertEqual(len(digest), 64)
        with self.assertRaises(ValueError): parse_price_page(page(), 'TT01011')
        with self.assertRaises(ValueError): parse_price_page(page(), '')
        with self.assertRaises(ValueError): parse_price_page(page(currency='USD'), 'TT01010')

    def test_missing_duplicate_and_malformed_offer_never_becomes_zero(self):
        for html in ['', '<html>unavailable</html>', page()+page(), '<script type="application/ld+json">bad</script>']:
            with self.subTest(html=html[:40]), self.assertRaises(ValueError):
                parse_price_page(html, 'TT01010')
        for number in ['0', '-1', 'NaN', 'Infinity', None, 'not a price']:
            with self.subTest(number=number), self.assertRaises(ValueError):
                parse_price_page(page(price=number), 'TT01010')

    def test_product_sku_fallback_and_offer_sku_precedence(self):
        product = {'@type': 'Product', 'sku': 'TT01010', 'offers': {'price':'10','priceCurrency':'EUR'}}
        html = lambda: '<script type="application/ld+json">'+json.dumps(product)+'</script>'
        self.assertEqual(parse_price_page(html(),'TT01010')[0], Decimal('10'))
        product['offers']['sku'] = 'OTHER'
        with self.assertRaises(ValueError): parse_price_page(html(),'TT01010')

    def test_source_allowlist_including_malformed_urls(self):
        for url in [URL, 'https://topciment.shop/products/acricem-25l']:
            self.assertTrue(allowed_source(url))
        for url in ['http://topciment.shop/products/a','https://topciment.shop.evil.test/products/a',
                    'https://topciment.shop@evil.test/products/a','https://x@topciment.shop/products/a',
                    URL+'?currency=USD', URL+'#x', 'https://topciment.shop:444/products/a',
                    'https://topciment.shop:invalid/products/a', 'https://[broken/products/a', None]:
            with self.subTest(url=url): self.assertFalse(allowed_source(url))

    def test_nbu_exact_currency_date_and_positive_rate(self):
        row = {'cc':'EUR','r030':978,'exchangedate':'24.09.2026','rate':51.3345}
        self.assertEqual(nbu_rate(json.dumps([row]),DAY),Decimal('51.3345'))
        # The requested date may be a weekend; compare actual NBU date, not weekday assumptions.
        weekend = dict(row,exchangedate='26.09.2026')
        self.assertEqual(nbu_rate(json.dumps([weekend]),date(2026,9,26)),Decimal('51.3345'))
        for change in [{'cc':'USD'},{'r030':840},{'exchangedate':'23.09.2026'},
                       {'exchangedate':'bad'},{'rate':0},{'rate':'NaN'},{'rate':'Infinity'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                nbu_rate(json.dumps([dict(row,**change)]),DAY)
        for payload in ['[]','{}',json.dumps([row,row])]:
            with self.assertRaises(ValueError): nbu_rate(payload,DAY)

    def test_refresh_preserves_source_custom_fields_and_original(self):
        old = {'url':URL,'manufacturer_sku':'TT01010','photo':'existing-image',
               'custom':{'manual':'keep'},'date':'2026-09-23','eur_pack':219.6}
        original = copy.deepcopy(old)
        new = refreshed_reference(old,'219.60','51.3345',DAY,'25','InStock')
        self.assertEqual(old,original)
        for key in ['url','manufacturer_sku','photo','custom']: self.assertEqual(new[key],old[key])
        self.assertEqual(new['date'],'2026-09-24')
        self.assertEqual(new['fx_date'],'2026-09-24')
        self.assertEqual(new['uah_pack'],11273.06)
        self.assertEqual(new['uah_unit'],450.92)
        self.assertEqual(refreshed_reference(new,'219.60','51.3345',DAY,'25','InStock'),new)
        self.assertNotEqual(refreshed_reference(new,'219.60','52',DAY,'25','InStock')['uah_pack'],new['uah_pack'])

    def test_half_up_and_invalid_pack(self):
        result=refreshed_reference({},'1.005','1',DAY,'2','')
        self.assertEqual(result['uah_pack'],1.01)
        self.assertEqual(result['uah_unit'],0.51)
        for pack in ['0','-1','NaN',None]:
            with self.subTest(pack=pack), self.assertRaises(ValueError):
                refreshed_reference({},'1','1',DAY,pack,'')

    def test_fetch_rejects_before_network_and_redirect_handler(self):
        with patch('apps.warehouse.topciment_prices.urllib.request.build_opener') as build:
            with self.assertRaises(ValueError): fetch('https://evil.test/',allowed_source)
            build.assert_not_called()
            response = io.BytesIO(b'hello')
            response.geturl = lambda: URL
            build.return_value.open.return_value = response
            self.assertEqual(fetch(URL,allowed_source),'hello')
            handler=build.call_args.args[0]
            with self.assertRaisesRegex(ValueError,'redirect_not_allowed'):
                handler.redirect_request(None,None,302,'',{},'https://evil.test/')

    def test_fetch_checks_final_url_and_size(self):
        for body,final in [(b'price','https://evil.test/'),(b'x'*2000001,URL)]:
            with self.subTest(final=final,size=len(body)):
                response=io.BytesIO(body);response.geturl=lambda:final
                with patch('apps.warehouse.topciment_prices.urllib.request.build_opener') as build:
                    build.return_value.open.return_value=response
                    with self.assertRaises(ValueError):fetch(URL,allowed_source)


class TopcimentCommandTests(TestCase):
    """Exercise command write boundaries using mocked ORM and HTTP; no DB connection."""
    def run_command(self, apply=False, concurrent=False, source_error=False):
        import contextlib
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from apps.warehouse.management.commands import sync_topciment_reference_prices as module
        reference={'url':URL,'manufacturer_sku':'TT01010','date':'2026-09-23',
                   'eur_pack':200,'eur_uah':50,'uah_pack':10000}
        product=SimpleNamespace(pk=3524,sku='TC-20260922-acricem',unit='л',
            is_active=True,pack_factor=Decimal('25'),price=Decimal('123'),
            shop_specs={'reference_price':copy.deepcopy(reference),'technical_facts':{'version':'old'}})
        live=copy.deepcopy(product)
        live.shop_specs['technical_facts']={'version':'concurrently edited'}
        live.shop_specs['translations']={'ru':{'full_description':'Preserve new text'}}
        if concurrent:live.shop_specs['reference_price']['eur_pack']=999
        live.save=MagicMock()
        manager=MagicMock()
        manager.filter.return_value.order_by.return_value=[product]
        manager.select_for_update.return_value.get.return_value=live
        def fetch_mock(url, allowed):
            if 'bank.gov.ua' in url:return 'mock NBU'
            if source_error:raise ValueError('source missing')
            return page()
        command=module.Command();command.stdout=io.StringIO()
        before=copy.deepcopy(live.shop_specs)
        error=None
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module.Product,'objects',manager), patch.object(module,'fetch',side_effect=fetch_mock), \
                 patch.object(module,'nbu_rate',return_value=Decimal('51.3345')), \
                 patch.object(module.transaction,'atomic',side_effect=contextlib.nullcontext):
                try:command.handle(apply=apply,ids=None,state_dir=directory)
                except module.CommandError as exc:error=exc
            from pathlib import Path
            report=json.loads((Path(directory)/('last-apply.json' if apply else 'last-dry-run.json')).read_text())
        return live,before,manager,error,report

    def test_dry_run_never_locks_or_saves_product(self):
        live,before,manager,error,report=self.run_command()
        self.assertIsNone(error)
        live.save.assert_not_called()
        manager.select_for_update.assert_not_called()
        self.assertEqual(live.shop_specs,before)
        self.assertTrue(report['dry_run'])
        self.assertEqual(report['statuses'],{'update':1})

    def test_source_failure_preserves_old_reference_and_retail(self):
        live,before,manager,error,report=self.run_command(apply=True,source_error=True)
        self.assertIsNotNone(error)
        live.save.assert_not_called()
        self.assertEqual(live.shop_specs,before)
        self.assertEqual(live.price,Decimal('123'))
        self.assertEqual(report['statuses'],{'held:source_error':1})

    def test_concurrent_reference_edit_is_not_overwritten(self):
        live,before,manager,error,report=self.run_command(apply=True,concurrent=True)
        self.assertIsNotNone(error)
        manager.select_for_update.assert_called_once()
        live.save.assert_not_called()
        self.assertEqual(live.shop_specs,before)
        self.assertEqual(report['statuses'],{'held:concurrent_change':1})

    def test_apply_merges_fresh_neighbors_without_touching_retail(self):
        live,before,manager,error,report=self.run_command(apply=True)
        self.assertIsNone(error)
        manager.select_for_update.assert_called_once()
        live.save.assert_called_once_with(update_fields=['shop_specs','updated_at'])
        self.assertEqual(live.shop_specs['technical_facts'],before['technical_facts'])
        self.assertEqual(live.shop_specs['translations'],before['translations'])
        self.assertEqual(live.price,Decimal('123'))
        self.assertEqual(live.shop_specs['reference_price']['uah_pack'],11273.06)
        self.assertEqual(report['statuses'],{'updated':1})
