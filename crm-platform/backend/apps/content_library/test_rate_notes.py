"""Product-owned calculator explanations without database access."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from apps.content_library import topciment as m

def product(key,notes=None,resin=None):
 specs={'topciment_key':key,'calculator_rates':{'microfino-wt':'2','efectto-wall':'0.3'},'acricem_l_per_kg':'0.3','primer_rate_l_m2':'0.1'}
 if notes is not None:specs['calculator_rate_notes']=notes
 if resin is not None:specs['calculator_resin_notes']=resin
 return SimpleNamespace(id=1,name='Product '+key,shop_specs=specs,price=Decimal(0),currency='UAH',unit='л' if key=='acricem' else 'кг',pack_factor=Decimal(20),updated_at=datetime(2026,9,23))
class CalculatorRateNotesTests(SimpleTestCase):
 def setUp(self):
  patcher=patch.object(m,"catalog")
  self.catalog=patcher.start()
  self.addCleanup(patcher.stop)
 def test_data_driven_selected_system_and_freshness(self):
  p=product('grip',{'efectto-wall':'  Selected explanation  ','efectto-floor':'Other'})
  self.catalog.return_value={'grip':p};a=m.calculate('efectto-wall',10,0)
  self.assertIn('Product grip: Selected explanation',a['notes']);self.assertFalse(any('Other' in n for n in a['notes']))
  p.shop_specs['calculator_rate_notes']['efectto-wall']='Changed'
  b=m.calculate('efectto-wall',10,0);self.assertIn('Product grip: Changed',b['notes']);self.assertNotIn('Product grip: Changed',a['notes'])
 def test_resin_dependency_and_dedup(self):
  note={'microfino-wt':'Same assumption'}
  self.catalog.return_value={'acricem':product('acricem'),'microbase':product('microbase',note,note),'microfino':product('microfino')}
  r=m.calculate('microfino-wt',10,0)
  self.assertEqual(r['notes'].count('Product microbase: Same assumption'),1)
  self.assertEqual(r['notes'][:len(m.NOTES)],m.NOTES)
 def test_malformed_ignored(self):
  for value in [None,[],7,'wrong',{'other':'Unselected'},{'efectto-wall':''},{'efectto-wall':'  '},{'efectto-wall':{}},{'efectto-wall':3}]:
   self.catalog.return_value={'grip':product('grip',value)}
   self.assertEqual(m.calculate('efectto-wall',10,0)['notes'],m.NOTES)
 def test_cap_and_math_unchanged(self):
  p=product('grip');self.catalog.return_value={'grip':p};before=m.calculate('efectto-wall',10,5)
  p.shop_specs['calculator_rate_notes']={'efectto-wall':'x'*900};after=m.calculate('efectto-wall',10,5)
  self.assertEqual(len(after['notes'][-1]),len('Product grip: ')+500)
  self.assertEqual({k:v for k,v in before.items() if k!='notes'},{k:v for k,v in after.items() if k!='notes'})
