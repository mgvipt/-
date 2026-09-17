import unittest
import json
import tempfile
import contextlib
import io
from pathlib import Path
from unittest.mock import patch
import sync

class ParserTest(unittest.TestCase):
    def sample(self, **changes):
        product={'databaseId':1416,'id':'stable','slug':'kolona-kl-101','name':'Колона KL 101','price':'840','regularPrice':'840','salePrice':None,'currencySymbol':'₴','description':'Ціна за 1 м.п. тіла колони','productCategories':{'nodes':[{'productCategoryACF':{'unit':['meter','м.п.']}}]}}
        product.update(changes)
        return product
    def parse(self,p,text='840 ₴',unit='м.п.'):
        text='<div class="flex items-baseline gap-2"><span>'+text+'</span></div><div class="flex items-center gap-1 mt-1"><span>за '+unit+'</span></div>'
        with patch('sync.unpack',return_value={'product':p}):
            return sync.parse_page({'databaseId':1416,'slug':'kolona-kl-101'},text)
    def test_partial_fetch_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            inv=Path(directory)/'inventory.json';out=Path(directory)/'snapshot.json'
            inv.write_text(json.dumps({'products':[{'databaseId':i,'slug':str(i)} for i in range(1,224)]}))
            out.write_text('previous verified snapshot')
            def get(url):
                if url.endswith('robots.txt'): return 'User-agent: *\nAllow: /'
                raise sync.urllib.error.HTTPError(url,429,'rate limited',None,None)
            with patch('sys.argv',['sync','--inventory',str(inv),'--output',str(out)]), patch.object(sync.Fetcher,'get',side_effect=get), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):sync.main()
            self.assertEqual('previous verified snapshot',out.read_text())

    def test_public_ssr_wrappers_and_empty_set(self):
        payload = [['ShallowReactive',1],{'data':2,'empty':5},{'product':3},{'databaseId':4},1416,['Set']]
        text = '<script id="__NUXT_DATA__">'+json.dumps(payload)+'</script>'
        self.assertEqual({'product':{'databaseId':1416}},sync.unpack(text))

    def test_price_unit_identity(self):
        p=self.parse(self.sample());self.assertEqual(('840','UAH','м.п.','verified'),(p['price'],p['currency'],p['unit'],p['status']))
        self.assertEqual(1416,p['sourceID'])
    def test_missing_price_is_null_not_zero(self):
        p=self.parse(self.sample(price=None,regularPrice=None,globalAttributes=None,allPaRozmir=None,galleryImages=None),'Уточнюйте ціну');self.assertIsNone(p['price']);self.assertEqual('price_on_request',p['status'])
    def test_public_purchase_price_wins_over_stale_ssr(self):
        p=self.parse(self.sample(),'841 ₴');self.assertEqual('841',p['price']);self.assertEqual('840',p['sourcePriceSSR']);self.assertEqual([],p['reviewIssues']);self.assertIn('visible_price_differs_from_SSR',p['sourceDiscrepancies'])
    def test_multiple_visible_prices_are_not_guessed(self):
        p=self.parse(self.sample(),'840 ₴ 900 ₴');self.assertEqual('review_required',p['status'])
    def test_identity_change_and_invalid_price_fail(self):
        for product in [self.sample(databaseId=999),self.sample(price='0'),self.sample(price='840–900')]:
            with self.assertRaises(ValueError):self.parse(product)
    def test_description_conflict_is_not_silently_converted(self):
        p=self.parse(self.sample(description='Ціна за штуку'));self.assertEqual('м.п.',p['unit']);self.assertEqual('review_required',p['status'])

if __name__=='__main__':unittest.main()
