from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Product
from .views import ProductViewSet
from .product_ordering import catalog_name


class ProductOrderTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='cezar-sort-test')
        self.factory = APIRequestFactory()
        self.rows = []
        for code, length, name, price in [
            ('LPC-20', 2000, 'Плинтус CEZAR 20', 100),
            ('LPC-19LE', 2440, 'Плінтус 19LE', 400),
            ('LPC-19', 2440, 'Плинтус 19 довгий', 300),
            ('LPC-01', 2440, 'Плінтус 01', 500),
            ('LPC-19', 2000, 'Плинтус 19 короткий', 200),
            ('LPC-29LE', 2440, 'Плінтус 29LE', 700),
            ('LPC-30', 2000, 'Плинтус 30', 600),
            ('LPC-29', 2000, 'Плінтус 29', 800),
        ]:
            self.rows.append(Product.objects.create(name=name, sku=f'{code}-{length}', price=price,
                shop_specs={'cezar': {'code': code, 'length': length}}))
        self.expected = [self.rows[i].id for i in [3,4,2,1,0,7,5,6]]

    def request(self, **params):
        request = self.factory.get('/api/products/', params)
        force_authenticate(request, self.user)
        response = ProductViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_natural_order_is_applied_before_pagination(self):
        first = self.request(page_size=3)
        second = self.request(page_size=3, page=2)
        third = self.request(page_size=3, page=3)
        actual = [p['id'] for response in [first,second,third] for p in response['results']]
        self.assertEqual(actual, self.expected)
        self.assertEqual(len(set(actual)),8)

    def test_explicit_price_and_name_order_is_preserved(self):
        for field in ['price', '-price', 'name', '-name']:
            actual = [p['id'] for p in self.request(ordering=field)['results']]
            self.assertEqual(actual, list(Product.objects.order_by(field,'id').values_list('id',flat=True)))

    def test_dashboard_key_has_same_model_and_length_order(self):
        self.assertEqual([p.id for p in sorted(self.rows, key=catalog_name)], self.expected)

    def test_other_products_keep_name_order(self):
        b=Product.objects.create(name='Other Beta',sku='b')
        a=Product.objects.create(name='Other Alpha',sku='a')
        self.assertEqual([p['id'] for p in self.request(search='Other')['results']],[a.id,b.id])
