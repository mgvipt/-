from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.accounts.models import User
from apps.warehouse.models import Product, ProductImage
from .models import Instruction
from .views import LibraryView

class ProductTrainingMirrorTests(TestCase):
 def setUp(self):
  self.user=User.objects.create(username='training-test',is_superuser=True)
  self.product=Product.objects.create(name='Test coating',price='100.00',unit='кг',description='Original text')
  self.entry=Instruction.objects.create(slug='training-test',title='Test',status='draft',content={'kind':'staff_training','section_key':'materials_decor','body':'Old copied text'})
  self.entry.products.add(self.product)
 def read(self):
  request=APIRequestFactory().get('/api/content-library/instructions/')
  force_authenticate(request,user=self.user)
  return LibraryView.as_view()(request)
 def test_price_description_and_gallery_follow_product_edits(self):
  first=self.read()
  self.assertEqual(first.data['training'][0]['products'][0]['price'],'100.00')
  Product.objects.filter(pk=self.product.pk).update(price='250.00',description='Updated application')
  im=ProductImage.objects.create(product=self.product,file_path='/tmp/test.jpg',alt_text='Test sample')
  second=self.read();p=second.data['training'][0]['products'][0]
  self.assertEqual(p['price'],'250.00');self.assertEqual(p['description'],'Updated application')
  self.assertEqual(p['images'][0]['id'],im.id)
  self.assertNotIn('body',second.data['training'][0])
  self.assertEqual(second['Cache-Control'],'private, no-store')
 def test_internal_training_is_not_a_public_client_guide(self):
  self.assertEqual(self.read().data['items'],[])
  request=APIRequestFactory().get('/api/content-library/instructions/')
  self.assertIn(LibraryView.as_view()(request).status_code,[401,403])
 def test_inactive_product_is_not_sold_by_library(self):
  Product.objects.filter(pk=self.product.pk).update(is_active=False)
  self.assertEqual(self.read().data['training'][0]['products'],[])

class TopcimentCalculationTests(TestCase):
 def setUp(self):
  self.p=self.product('eq-small',pack=6,rates={'efectto-wall':'0.25'},reference_price={'uah_pack':1200})
  self.grip=self.product('grip',pack=5,rates={'efectto-wall':'0.375'})
  self.wt_a=self.product('wt-mate',unit='л',pack=5,rates={'efectto-wall':'0.22'},mixing={'a_to_b_mass':'5','density_a_kg_l':'1.03','density_b_kg_l':'1.14','b_pack_count':1})
  self.wt_b=self.product('wt-b',unit='л',pack=1)
 def product(self,key,unit='кг',pack=20,rates=None,**specs):
  return Product.objects.create(name=key,sku='TC-20260922-'+key,price='100',currency='UAH',unit=unit,pack_factor=pack,shop_specs={'topciment_key':key,'calculator_rates':rates or {},**specs})
 def row(self,key,system='efectto-wall',area=25,reserve=0,basis='sale'):
  from .topciment import calculate
  return next(r for r in calculate(system,area,reserve,basis)['rows'] if r['key']==key)
 def update_specs(self,product,**changes):
  product.refresh_from_db()
  Product.objects.filter(pk=product.pk).update(shop_specs={**product.shop_specs,**changes})
 def test_whole_packs_and_current_price(self):
  from .topciment import calculate
  for area,qty,packs in [(1,.25,1),(25,6.25,2),(100,25,5)]:
   r=calculate('efectto-wall',area,0)
   row=next(x for x in r['rows'] if x['key']=='eq-small')
   self.assertEqual(row['quantity'],qty);self.assertEqual(row['packs'],packs)
   self.assertEqual(row['subtotal'],600*packs)
   self.assertFalse(r['complete']);self.assertTrue(r['missing'])
  Product.objects.filter(pk=self.p.pk).update(price=200)
  row=next(x for x in calculate('efectto-wall',25,0)['rows'] if x['key']=='eq-small')
  self.assertEqual(row['subtotal'],2400)
 def test_reserve_and_reference_are_separate(self):
  from .topciment import calculate
  row=next(x for x in calculate('efectto-wall',24,10,'reference')['rows'] if x['key']=='eq-small')
  self.assertEqual(row['quantity'],6.6);self.assertEqual(row['packs'],2);self.assertEqual(row['subtotal'],2400)
  self.p.refresh_from_db();self.assertEqual(self.p.price,100)
 def test_invalid_and_nonfinite_inputs(self):
  from .topciment import calculate
  for area,reserve in [(0,0),(-1,0),('NaN',0),('Infinity',0),(1,51),(1,-1)]:
   with self.assertRaises((ValueError,ArithmeticError)):calculate('efectto-wall',area,reserve)
 def test_grip_units_and_wt_kit_yield(self):
  from .topciment import calculate
  rows={r['key']:r for r in calculate('efectto-wall',100,0)['rows']}
  self.assertEqual(rows['grip']['quantity'],37.5)
  self.assertEqual(rows['wt-kit']['packs'],4)
  self.assertAlmostEqual(rows['wt-kit']['pack'],5.904,places=3)
 def test_missing_or_inactive_material_keeps_identity_and_unknown_norm(self):
  for inactive in (False,True):
   with self.subTest(inactive=inactive):
    if inactive:Product.objects.filter(pk=self.p.pk).update(is_active=False)
    key='eq-small' if inactive else 'eq-big'
    row=self.row(key)
    self.assertNotIn('XZ',row['name'])
    self.assertIn('Small Grain' if inactive else 'Big Grain',row['name'])
    self.assertEqual(row['unit'],'кг')
    self.assertIsNone(row['rate']);self.assertIsNone(row['quantity'])
    self.assertIsNone(row['subtotal']);self.assertEqual(row['products'],[])
 def test_invalid_pack_or_changed_unit_cannot_produce_order(self):
  for pack,unit in [(0,'кг'),(-1,'кг'),(6,'л'),(6,'уп')]:
   with self.subTest(pack=pack,unit=unit):
    Product.objects.filter(pk=self.p.pk).update(pack_factor=pack,unit=unit)
    row=self.row('eq-small')
    self.assertEqual(row['quantity'],6.25)
    self.assertEqual(row['unit'],'кг')
    self.assertIsNone(row['packs']);self.assertIsNone(row['subtotal'])
    self.assertIn('перевірте',row['name'])
 def test_unknown_sale_price_does_not_become_free_material(self):
  for price,currency in [(0,'UAH'),(100,'EUR')]:
   with self.subTest(price=price,currency=currency):
    Product.objects.filter(pk=self.p.pk).update(price=price,currency=currency)
    row=self.row('eq-small')
    self.assertEqual(row['packs'],2);self.assertIsNone(row['subtotal'])
    self.assertEqual(self.row('eq-small',basis='reference')['subtotal'],2400)
 def test_updated_card_norm_is_used_on_next_calculation(self):
  self.assertEqual(self.row('eq-small')['quantity'],6.25)
  self.update_specs(self.p,calculator_rates={'efectto-wall':'0.5'})
  row=self.row('eq-small')
  self.assertEqual(row['quantity'],12.5);self.assertEqual(row['packs'],3)
  self.assertEqual(row['subtotal'],1800)
 def test_absent_or_invalid_norm_is_not_silently_zero(self):
  self.update_specs(self.p,calculator_rates={})
  row=self.row('eq-small')
  self.assertIsNone(row['quantity']);self.assertIsNone(row['subtotal'])
  from .topciment import calculate
  for rate in ['0','-1','NaN','Infinity','bad']:
   with self.subTest(rate=rate):
    self.update_specs(self.p,calculator_rates={'efectto-wall':rate})
    with self.assertRaises((ValueError,ArithmeticError)):calculate('efectto-wall',25,0)
 def test_acricem_is_derived_from_current_powder_and_mixing_rates(self):
  self.product('acricem',unit='л',pack=25,primer_rate_l_m2='0.1')
  base=self.product('microbase',rates={'microdeck-dsv':'2.1'},acricem_l_per_kg='0.3')
  deck=self.product('microdeck',rates={'microdeck-dsv':'1'},acricem_l_per_kg='0.3')
  row=self.row('acricem',system='microdeck-dsv')
  self.assertEqual(row['rate'],1.03);self.assertEqual(row['quantity'],25.75)
  self.assertEqual(row['packs'],2)
  self.update_specs(deck,calculator_rates={'microdeck-dsv':'2'})
  self.assertEqual(self.row('acricem',system='microdeck-dsv')['rate'],1.33)
  self.update_specs(base,acricem_l_per_kg='0.4')
  self.assertEqual(self.row('acricem',system='microdeck-dsv')['rate'],1.54)
  self.update_specs(deck,acricem_l_per_kg=None)
  self.assertIsNone(self.row('acricem',system='microdeck-dsv')['quantity'])
 def test_wt_uses_current_densities_and_component_prices(self):
  row=self.row('wt-kit',area=100)
  self.assertEqual(row['packs'],4);self.assertEqual(row['subtotal'],2400)
  Product.objects.filter(pk=self.wt_b.pk).update(price=200)
  self.assertEqual(self.row('wt-kit',area=100)['subtotal'],2800)
  self.update_specs(self.wt_a,mixing={'a_to_b_mass':'5','density_a_kg_l':'1','density_b_kg_l':'1','b_pack_count':1})
  self.assertEqual(self.row('wt-kit')['pack'],6)
 def test_wt_incomplete_components_or_metadata_block_priced_kit(self):
  for field,value in [('price',0),('pack_factor',0),('pack_factor',-1),('unit','кг'),('is_active',False)]:
   with self.subTest(field=field,value=value):
    Product.objects.filter(pk=self.wt_b.pk).update(price=100,pack_factor=1,unit='л',is_active=True)
    Product.objects.filter(pk=self.wt_b.pk).update(**{field:value})
    self.assertIsNone(self.row('wt-kit')['subtotal'])
  Product.objects.filter(pk=self.wt_b.pk).update(is_active=True)
  self.update_specs(self.wt_a,mixing={})
  self.assertIsNone(self.row('wt-kit')['pack'])
  self.assertIsNone(self.row('wt-kit')['subtotal'])
 def test_dsv_two_b_packs_are_included_in_price_and_yield(self):
  self.product('dsv-a',unit='л',pack=4,rates={'microdeck-dsv':'0.2'},mixing={'b_pack_count':2})
  self.product('dsv-b',unit='л',pack=1)
  row=self.row('dsv-kit',system='microdeck-dsv',area=100)
  self.assertEqual(row['quantity'],20);self.assertEqual(row['pack'],6)
  self.assertEqual(row['packs'],4);self.assertEqual(row['subtotal'],2400)
 def test_invalid_system_and_basis_are_rejected(self):
  from .topciment import calculate
  with self.assertRaises(ValueError):calculate('unknown',25,0)
  with self.assertRaises(ValueError):calculate('efectto-wall',25,0,'unknown')
 def test_acricem_missing_primer_or_incompatible_powder_units_stays_unknown(self):
  acricem=self.product('acricem',unit='л',pack=25)
  base=self.product('microbase',rates={'microdeck-dsv':'2.1'},acricem_l_per_kg='0.3')
  self.product('microdeck',rates={'microdeck-dsv':'1'},acricem_l_per_kg='0.3')
  self.assertIsNone(self.row('acricem',system='microdeck-dsv')['quantity'])
  self.update_specs(acricem,primer_rate_l_m2='0.1')
  self.assertEqual(self.row('acricem',system='microdeck-dsv')['rate'],1.03)
  Product.objects.filter(pk=base.pk).update(unit='л')
  self.assertIsNone(self.row('acricem',system='microdeck-dsv')['rate'])
  Product.objects.filter(pk=base.pk).update(unit='кг')
  Product.objects.filter(pk=acricem.pk).update(unit='кг')
  self.assertIsNone(self.row('acricem',system='microdeck-dsv')['rate'])
 def test_negative_resin_norm_cannot_cancel_positive_powder_consumption(self):
  self.product('acricem',unit='л',pack=25,primer_rate_l_m2='0.1')
  self.product('microbase',rates={'microdeck-dsv':'2.1'},acricem_l_per_kg='-0.01')
  self.product('microdeck',rates={'microdeck-dsv':'1'},acricem_l_per_kg='0.3')
  with self.assertRaises(ValueError):self.row('acricem',system='microdeck-dsv')
 def test_kit_name_is_friendly_even_when_owner_is_absent(self):
  Product.objects.filter(pk=self.wt_a.pk).update(is_active=False)
  row=self.row('wt-kit')
  self.assertIn('Topsealer WT',row['name'])
  self.assertNotIn('wt-kit',row['name']);self.assertNotIn('5 л',row['name'])
  self.assertIsNone(row['rate'])
 def test_wt_component_counts_and_pack_changes_update_yield_and_price(self):
  Product.objects.filter(pk=self.wt_a.pk).update(pack_factor=10)
  mix={'a_to_b_mass':'5','density_a_kg_l':'1','density_b_kg_l':'1','b_pack_count':1}
  self.update_specs(self.wt_a,mixing=mix)
  self.assertEqual(self.row('wt-kit')['pack'],6)
  self.assertEqual(self.row('wt-kit')['pack_price'],1100)
  self.update_specs(self.wt_a,mixing={**mix,'b_pack_count':2})
  row=self.row('wt-kit')
  self.assertEqual(row['pack'],12);self.assertEqual(row['pack_price'],1200)
  self.assertNotIn('5 л',row['name']);self.assertNotIn('1 л',row['name'])
 def test_wt_nonpositive_density_ratio_or_count_is_rejected(self):
  mix={'a_to_b_mass':'5','density_a_kg_l':'1.03','density_b_kg_l':'1.14','b_pack_count':1}
  for key in mix:
   for bad in ('0','-1','NaN','Infinity'):
    with self.subTest(key=key,bad=bad):
     self.update_specs(self.wt_a,mixing={**mix,key:bad})
     with self.assertRaises((ValueError,ArithmeticError)):self.row('wt-kit')
  self.update_specs(self.wt_a,mixing={**mix,'b_pack_count':'1.5'})
  with self.assertRaises(ValueError):self.row('wt-kit')
 def test_missing_density_or_pack_count_cannot_produce_priced_kit(self):
  mix={'a_to_b_mass':'5','density_a_kg_l':'1.03','density_b_kg_l':'1.14','b_pack_count':1}
  for key in mix:
   with self.subTest(key=key):
    self.update_specs(self.wt_a,mixing={k:v for k,v in mix.items() if k!=key})
    row=self.row('wt-kit')
    self.assertIsNone(row['pack']);self.assertIsNone(row['subtotal'])
 def test_notes_do_not_repeat_stale_numeric_norms(self):
  from .topciment import NOTES
  self.assertFalse(any(character.isdigit() for note in NOTES for character in note))

class CanonicalClientArticleTests(TestCase):
 def setUp(self):
  self.p=Product.objects.create(name='Матеріал',shop_short_description='Коротко українською',shop_full_description='Переваги\nУкраїнський текст',shop_specs={'translations':{'ru':{'short_description':'Кратко по-русски','full_description':'Преимущества\nРусский текст','article_title':'Материал'}}})
  self.i=Instruction.objects.create(slug='material-test',title='Матеріал',status='published',content={'kind':'client_material','primary_product_id':self.p.id})
  self.i.products.add(self.p)
 def test_article_tracks_product_edits_and_language(self):
  from .client_materials import material_article
  self.assertEqual(material_article(self.i,'ru')['intro'],'Кратко по-русски')
  Product.objects.filter(pk=self.p.pk).update(shop_full_description='Новий опис без копії')
  self.assertIn('Новий опис без копії',material_article(self.i)['body_html'])
  self.assertNotIn('body',self.i.content)
 def test_article_escapes_product_text(self):
  from .client_materials import material_article
  Product.objects.filter(pk=self.p.pk).update(shop_full_description='<script>alert(1)</script>')
  self.assertNotIn('<script>',material_article(self.i)['body_html'])
 def test_product_patch_rejects_stale_version(self):
  from apps.warehouse.views import ProductViewSet
  user=User.objects.create(username='product-editor',is_superuser=True)
  request=APIRequestFactory().patch('/api/products/%s/'%self.p.id,{'expected_updated_at':'2020-01-01T00:00:00Z','name':'Overwritten'},format='json')
  force_authenticate(request,user=user)
  response=ProductViewSet.as_view({'patch':'partial_update'})(request,pk=self.p.id)
  self.assertEqual(response.status_code,409)
  self.p.refresh_from_db();self.assertEqual(self.p.name,'Матеріал')

class CanonicalAIMaterialTests(TestCase):
 def test_ai_facts_follow_card_without_kb_copy(self):
  from apps.knowledge.catalog import current_product_facts
  p=Product.objects.create(name='Sirena Silk',price=100,unit='кг',description='Перший опис')
  i=Instruction.objects.create(slug='ai-source-test',title='Sirena',content={'kind':'staff_training'})
  i.products.add(p)
  self.assertIn('Перший опис',current_product_facts(query='Sirena Silk'))
  Product.objects.filter(pk=p.pk).update(description='Змінений опис',price=150)
  text=current_product_facts(query='Sirena Silk')
  self.assertIn('Змінений опис',text);self.assertIn('150.00',text);self.assertNotIn('Перший опис',text)
  Product.objects.filter(pk=p.pk).update(is_active=False)
  self.assertEqual(current_product_facts(query='Sirena Silk'),'')


class TopcimentTechnicalReviewTests(TestCase):
 setUp=TopcimentCalculationTests.setUp
 product=TopcimentCalculationTests.product
 row=TopcimentCalculationTests.row
 update_specs=TopcimentCalculationTests.update_specs
 def flag(self,product,required=True):
  self.update_specs(product,technical_facts={'schema_version':1,'technical_review':{'required':required,'codes':['internal-code-not-for-ui']},'density':[{'source':{'revision':'2026-05'}}]})
 def test_review_blocks_complete_without_changing_calculation(self):
  from .topciment import calculate
  system={'id':'efectto-wall','name':'Test','materials':['eq-small']}
  with patch('apps.content_library.topciment.SYSTEMS',[system]):
   before=calculate('efectto-wall',25,0)
   self.assertTrue(before['complete'])
   self.flag(self.p)
   after=calculate('efectto-wall',25,0)
   self.assertFalse(after['complete']);self.assertEqual(after['missing'],[])
   self.assertEqual(after['known_total'],before['known_total'])
   row=after['rows'][0]
   for field in ('rate','quantity','packs','pack_price','subtotal'):
    self.assertEqual(row[field],before['rows'][0][field])
   self.assertTrue(row['needs_review'])
   self.assertEqual(after['technical_unverified'][0]['products'][0]['id'],self.p.id)
   self.assertEqual(row['products'][0]['source_revisions'],['2026-05'])
   self.assertTrue(row['products'][0]['updated_at'])
   self.assertNotIn('internal-code-not-for-ui',str(after))
   self.flag(self.p,False)
   self.assertTrue(calculate('efectto-wall',25,0)['complete'])
 def test_component_b_review_marks_kit(self):
  before=self.row('wt-kit');self.flag(self.wt_b)
  after=self.row('wt-kit')
  self.assertTrue(after['needs_review'])
  self.assertEqual(after['quantity'],before['quantity']);self.assertEqual(after['subtotal'],before['subtotal'])
  self.assertIn(self.wt_b.id,[p['id'] for p in after['products'] if p['needs_review']])
 def test_powder_review_propagates_to_derived_acricem(self):
  self.product('acricem',unit='л',pack=25,primer_rate_l_m2='0.1')
  self.product('microbase',rates={'microdeck-dsv':'2.1'},acricem_l_per_kg='0.3')
  deck=self.product('microdeck',rates={'microdeck-dsv':'1'},acricem_l_per_kg='0.3')
  self.flag(deck)
  row=self.row('acricem',system='microdeck-dsv')
  self.assertTrue(row['needs_review']);self.assertEqual(row['rate'],1.03)
  self.assertIn(deck.id,[p['id'] for p in row['products'] if p['needs_review']])
 def test_unknown_norm_keeps_review_and_card_link(self):
  self.flag(self.p);self.update_specs(self.p,calculator_rates={})
  row=self.row('eq-small')
  self.assertIsNone(row['quantity']);self.assertTrue(row['needs_review'])
  self.assertEqual(row['products'][0]['id'],self.p.id)
 def test_quote_required_hides_positive_sale_price_only(self):
  self.update_specs(self.p,price_status='quote_required')
  self.assertIsNone(self.row('eq-small')['subtotal'])
  self.assertEqual(self.row('eq-small',basis='reference')['subtotal'],2400)
  self.update_specs(self.wt_b,price_status='quote_required')
  self.assertIsNone(self.row('wt-kit')['subtotal'])
