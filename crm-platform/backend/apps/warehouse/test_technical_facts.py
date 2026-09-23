from copy import deepcopy
from unittest.mock import patch
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.accounts.models import User
from apps.content_library.models import Instruction
from apps.content_library.views import LibraryView
from .models import Product
from .technical_facts import technical_data, validate_technical_facts, ProductTechnicalSheet
from .product_source import product_data
from .shop_sync import normalized_shop_specs

class TechnicalFactsTests(TestCase):
    def setUp(self):
        self.user=User.objects.create(username='technical-test',is_superuser=True)
        self.fact={'id':'density-a','state':'liquid','component':'A','value':1.03,'uncertainty':0.01,'unit':'kg/L','status':'confirmed','source':{'url':'https://www.topciment.com/sheets/test.pdf','revision':'2024-07','page':2},'original':{'value':1.03,'unit':'g/cm³'}}
        self.tech={'schema_version':1,'density':[self.fact],'technical_review':{'required':True,'codes':['test']}}
        self.product=Product.objects.create(name='Technical',price=100,unit='л',pack_factor=5,shop_specs={'technical_facts':self.tech,'mixing':{'density_a_kg_l':'1.03'}})
    def test_invalid_values_states_units_are_never_confirmed(self):
        for patch in [{'value':0},{'value':-1},{'value':'NaN'},{'value':'Infinity'},{'state':'other'},{'component':'C'},{'unit':'g/m3'},{'uncertainty':2}]:
            with self.subTest(patch=patch):
                item={**self.fact,**patch};self.product.shop_specs={'technical_facts':{**self.tech,'density':[item]}}
                row=technical_data(self.product)['density'][0]
                self.assertEqual(row['status'],'unknown');self.assertIsNone(row['value'])
                with self.assertRaises(ValueError):validate_technical_facts(self.product.shop_specs['technical_facts'])
    def test_range_valid_and_reversed_rejected(self):
        self.product.shop_specs['technical_facts']['density']=[{**self.fact,'value':None,'uncertainty':None,'min':1,'max':1.2}]
        self.assertEqual(technical_data(self.product)['density'][0]['status'],'confirmed')
        self.product.shop_specs['technical_facts']['density'][0]['min']=2
        self.assertEqual(technical_data(self.product)['density'][0]['status'],'unknown')
    def test_read_does_not_mutate_product_or_enable_dosing(self):
        before=deepcopy(self.product.shop_specs);result=technical_data(self.product)
        self.assertFalse(result['density'][0]['dosing_conversion_allowed']);self.assertEqual(self.product.shop_specs,before)
        self.assertEqual(product_data(self.product)['technical'],result)
    def test_live_library_and_sheet_follow_product_without_instruction_copy(self):
        ins=Instruction.objects.create(slug='technical-mirror',title='Technical',status='draft',content={'kind':'staff_training'})
        ins.products.add(self.product)
        def read(view,url):
            request=APIRequestFactory().get(url);force_authenticate(request,user=self.user);return view.as_view()(request)
        initial=read(LibraryView,'/?lang=uk').data['training'][0]['products'][0]['technical']
        self.assertEqual(initial,technical_data(self.product))
        self.tech['density'][0]['value']=1.2;Product.objects.filter(pk=self.product.id).update(shop_specs={'technical_facts':self.tech})
        updated=read(LibraryView,'/?lang=ru').data['training'][0]['products'][0]['technical']
        sheet=read(ProductTechnicalSheet,f'/?ids={self.product.id}&lang=ru')
        self.assertEqual(updated,sheet.data['items'][0]['technical']);self.assertEqual(updated['density'][0]['value'],1.2)
        self.assertEqual(sheet['Cache-Control'],'private, no-store');self.assertEqual(sheet.data['items'][0]['pack_factor'],str(Product.objects.get(pk=self.product.pk).pack_factor))
        ins.refresh_from_db();self.assertNotIn('technical_facts',ins.content)
    def test_sheet_rejects_unauthenticated_and_unprivileged(self):
        request=APIRequestFactory().get('/?ids=1');self.assertIn(ProductTechnicalSheet.as_view()(request).status_code,[401,403])
        user=User.objects.create(username='technical-unprivileged');force_authenticate(request,user=user)
        with patch.object(user, 'has_perm_code', return_value=False):
            self.assertEqual(ProductTechnicalSheet.as_view()(request).status_code,403)
    def test_internal_metadata_does_not_enter_shop(self):
        source={'technical_facts':self.tech,'finish':'matte','mixing':{'density_a_kg_l':'1.03'}}
        result=normalized_shop_specs(source)
        self.assertNotIn('technical_facts',result);self.assertIn('technical_facts',source);self.assertEqual(result['finish'],'matte')

    def test_inactive_or_customer_superuser_cannot_read_sheet(self):
        for field, value in [('is_active', False), ('account_kind', 'customer')]:
            original=getattr(self.user,field);setattr(self.user,field,value)
            request=APIRequestFactory().get(f'/?ids={self.product.id}')
            force_authenticate(request,user=self.user)
            self.assertEqual(ProductTechnicalSheet.as_view()(request).status_code,403)
            setattr(self.user,field,original)
    def test_quote_required_and_zero_prices_are_not_operational(self):
        for price, specs in [(0, {}), (100, {'price_status':'quote_required'}), (-1,{})]:
            Product.objects.filter(pk=self.product.pk).update(price=price,shop_specs=specs)
            request=APIRequestFactory().get(f'/?ids={self.product.id}')
            force_authenticate(request,user=self.user)
            row=ProductTechnicalSheet.as_view()(request).data['items'][0]
            self.assertIsNone(row['price']);self.assertEqual(row['price_status'],'quote_required')
