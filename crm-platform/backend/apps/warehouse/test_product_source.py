import hashlib
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Product
from apps.inbox.models import MediaLibraryItem, SharedLink


class ProductSourceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = get_user_model().objects.create_user(username='source-test-owner', is_superuser=True)
        self.product = Product.objects.create(name='Тестовий матеріал', unit='л', price='123.45',
            cost='70', description='Ручний опис', shop_specs={'custom': 'keep'})

    def facts(self):
        return '/api/products/%d/facts/' % self.product.id

    def test_integration_key_only_and_no_customer_or_cost_fields(self):
        with patch.dict('os.environ', {'CRM_PRODUCT_READ_TOKEN_SHA256': hashlib.sha256(b'test-key').hexdigest()}):
            self.assertEqual(self.client.get('/api/product-source/').status_code, 403)
            self.client.force_authenticate(self.owner)
            self.assertEqual(self.client.get('/api/product-source/').status_code, 403)
            self.client.credentials(HTTP_AUTHORIZATION='Bearer test-key')
            response = self.client.get('/api/product-source/')
            self.assertEqual(response.status_code, 200)
            product = response.json()['items'][0]
            self.assertEqual(product['price'], '123.45')
            self.assertNotIn('cost', product)
            self.assertNotIn('custom', product['shop_specs'])
            self.assertEqual(self.client.post('/api/product-source/', {}, format='json').status_code, 405)

    def test_facts_preserves_commercial_fields_and_rejects_stale_write(self):
        self.client.force_authenticate(self.owner)
        stamp = self.client.get(self.facts()).json()['updated_at']
        payload = {'updated_at': stamp, 'shop_specs': {'consumption_range': {'min': '0.075', 'max': '0.15', 'unit': 'кг/м²'}}}
        with patch('apps.warehouse.shop_sync.queue_product_sync') as queue:
            self.assertEqual(self.client.patch(self.facts(), payload, format='json').status_code, 200)
            queue.assert_not_called()
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), '123.45')
        self.assertEqual(self.product.unit, 'л')
        self.assertEqual(self.product.description, 'Ручний опис')
        self.assertEqual(self.product.shop_specs['custom'], 'keep')
        self.assertIsNone(self.product.consumption_per_m2)
        self.assertEqual(self.client.patch(self.facts(), payload, format='json').status_code, 409)

    def test_invalid_ranges_and_price_writes_rejected(self):
        self.client.force_authenticate(self.owner)
        stamp = self.client.get(self.facts()).json()['updated_at']
        for value in ({'min':'0.75','max':'0.15','unit':'кг/м²'}, {'min':'NaN','max':'1','unit':'кг/м²'}):
            self.assertEqual(self.client.patch(self.facts(), {'updated_at':stamp,'shop_specs':{'consumption_range':value}}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(self.facts(), {'updated_at':stamp,'price':'1'}, format='json').status_code, 400)

    def test_media_uses_current_reference_and_excludes_other_products(self):
        self.client.force_authenticate(self.owner)
        file = SharedLink.objects.create(token='testproductmedia123456', filename='test.jpg', data=b'test')
        item = MediaLibraryItem.objects.create(title='Original caption', tags='product:%d' % self.product.id, file=file)
        MediaLibraryItem.objects.create(title='Other', tags='product:%d0' % self.product.id, file=file)
        MediaLibraryItem.objects.create(title='Rejected', tags='product:%d rejected_by_user' % self.product.id, file=file)
        self.assertEqual([x['title'] for x in self.client.get(self.facts()).json()['media']], ['Original caption'])
        item.title='Updated caption'; item.save(update_fields=['title'])
        self.assertEqual(self.client.get(self.facts()).json()['media'][0]['title'], 'Updated caption')
        self.assertEqual(SharedLink.objects.count(), 1)

    def test_anonymous_cannot_read_facts(self):
        self.assertIn(self.client.get(self.facts()).status_code, (401,403))

    def test_russian_facts_edit_preserves_ukrainian_and_unrelated_specs(self):
        self.client.force_authenticate(self.owner)
        self.product.shop_full_description = 'Українська повна інструкція'
        self.product.shop_specs = {'custom': 'keep', 'application': 'Стіни', 'translations': {'ru': {'full_description': 'Русская инструкция', 'name': 'Название'}, 'en': {'description': 'Keep'}}}
        self.product.save()
        url = self.facts() + '?lang=ru'
        old = self.client.get(url).json()
        self.assertEqual(old['shop_full_description'], 'Русская инструкция')
        payload = {'updated_at': old['updated_at'], 'shop_full_description': 'Подробная русская инструкция', 'shop_specs': {'application': 'Стены', 'finish': 'Финиш по образцу'}}
        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['shop_specs']['finish'], 'Финиш по образцу')
        self.product.refresh_from_db()
        self.assertEqual(self.product.shop_full_description, 'Українська повна інструкція')
        self.assertEqual(self.product.shop_specs['application'], 'Стіни')
        self.assertEqual(self.product.shop_specs['translations']['ru']['full_description'], 'Подробная русская инструкция')
        self.assertEqual(self.product.shop_specs['translations']['ru']['name'], 'Название')
        self.assertEqual(self.product.shop_specs['translations']['en']['description'], 'Keep')
        self.assertEqual(self.product.shop_specs['custom'], 'keep')
        self.assertEqual(self.client.get(self.facts()).json()['shop_full_description'], 'Українська повна інструкція')
        self.assertEqual(self.client.patch(url, payload, format='json').status_code, 409)

    def test_consumption_is_shared_when_editing_russian(self):
        self.client.force_authenticate(self.owner)
        url = self.facts() + '?lang=ru'
        old = self.client.get(url).json()
        value = {'min': '0.2', 'max': '0.25', 'unit': 'кг/м²'}
        self.assertEqual(self.client.patch(url, {'updated_at': old['updated_at'], 'shop_specs': {'consumption_range': value}}, format='json').status_code, 200)
        self.assertEqual(self.client.get(self.facts()).json()['shop_specs']['consumption_range'], value)

    def test_blank_translation_has_visible_fallback_metadata(self):
        self.client.force_authenticate(self.owner)
        self.product.shop_full_description = 'Повна інструкція'
        self.product.shop_specs = {'translations': {'ru': {'full_description': '   '}}}
        self.product.save()
        data = self.client.get(self.facts() + '?lang=ru').json()
        self.assertEqual(data['shop_full_description'], 'Повна інструкція')
        self.assertIn('shop_full_description', data['fallback_fields'])
