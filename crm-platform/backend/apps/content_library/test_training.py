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
