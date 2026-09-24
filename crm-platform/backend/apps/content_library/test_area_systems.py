from datetime import datetime
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from apps.content_library import topciment

class AreaSystemTests(SimpleTestCase):
 def product(self,key,unit='кг',rate='2',resin='0.3'):
  return SimpleNamespace(id=hash(key)%100000,name=key,unit=unit,price=D(10),currency='UAH',pack_factor=D(18),updated_at=datetime(2026,9,24),shop_specs={'topciment_key':key,'calculator_rates':{sid:rate for sid in ('sttandard-wall','sttandard-floor','sttandard-exterior')},'acricem_l_per_kg':resin,'primer_rate_l_m2':'99'})
 def test_three_current_six_historical(self):
  self.assertEqual(sum(not s['historical'] for s in topciment.SYSTEMS),3)
  self.assertEqual(sum(s['historical'] for s in topciment.SYSTEMS),6)
 def test_no_unlimitted_substitution(self):
  with patch.object(topciment,'catalog',return_value={'microdeck':self.product('microdeck')}):
   result=topciment.calculate('sttandard-floor',10,0,substrate='abs')
  rows={r['key']:r for r in result['rows']}
  self.assertNotIn('microdeck',rows)
  self.assertIsNone(rows['sttandard-microdeck']['quantity'])
  self.assertFalse(result['complete'])
 def test_explicit_primer_and_resin_no_double_priming(self):
  products={k:self.product(k,'л' if k in ('abs','plus','acricem') else 'кг') for k in ('abs','plus','acricem','microbase','microfino')}
  with patch.object(topciment,'catalog',return_value=products):
   result=topciment.calculate('sttandard-wall',10,0,substrate='plus')
   unknown=topciment.calculate('sttandard-wall',10,0)
  rows={r['key']:r for r in result['rows']}
  self.assertIn('plus',rows);self.assertNotIn('abs',rows)
  self.assertEqual(rows['acricem']['quantity'],12)
  self.assertTrue(any(r['key']=='primer-choice' and r['quantity'] is None for r in unknown['rows']))
 def test_dragon_no_b_no_pack_no_price(self):
  products={'dragon-mate-a':self.product('dragon-mate-a','л','0.2')}
  with patch.object(topciment,'catalog',return_value=products):
   result=topciment.calculate('sttandard-exterior',10,0,substrate='abs')
  row=next(r for r in result['rows'] if r['key']=='dragon-kit')
  self.assertEqual(row['quantity'],2)
  self.assertIsNone(row['pack']);self.assertIsNone(row['subtotal'])
  self.assertIn('A + B',row['name'])
 def test_invalid_substrate_rejected(self):
  with self.assertRaises(ValueError):topciment.calculate('sttandard-wall',10,0,substrate='wt-b')
 def test_review_reasons_and_https_sources(self):
  p=self.product('microbase')
  p.shop_specs['technical_facts']={'technical_review':{'required':True,'codes':['wt_family_substitution']},'density':[{'source':{'url':'javascript:alert(1)'}},{'source':{'url':'https://www.topciment.com/sheets/example.pdf'}}]}
  p.shop_specs['calculator_system_review']={'sttandard-wall':{'required':True,'reason':'Перевірити основу перед нанесенням.'}}
  with patch.object(topciment,'catalog',return_value={'microbase':p}):result=topciment.calculate('sttandard-wall',10,0)
  product=next(r for r in result['rows'] if r['key']=='microbase')['products'][0]
  self.assertEqual(len(product['review_reasons']),2)
  self.assertEqual(product['source_urls'],['https://www.topciment.com/sheets/example.pdf'])
