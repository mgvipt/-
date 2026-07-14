import hashlib
import hmac
import json
import time
import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.crm.models import Contact, Deal, Funnel, Stage
from .models import ShopOrderImport


@override_settings(SHOP_WEBHOOK_SECRET="test-shop-secret")
class ShopOrderWebhookTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        for name in ("21 Основний продукт", "22 Тестовий набір"):
            funnel = Funnel.objects.create(name=name)
            Stage.objects.create(funnel=funnel, name="Данні для розрахунку", order=0)

    def test_signed_order_is_imported_once(self):
        event_uuid = str(uuid.uuid4())
        payload = {
            "event_uuid": event_uuid,
            "order": {
                "number": "WV-TEST-1", "customer_name": "Олег Тест", "phone": "+380501112233",
                "email": "test@example.com", "total": "1250.00", "payment_method": "after_confirmation",
                "city": "Київ", "delivery_branch": "Відділення 1", "customer_comment": "Подзвоніть",
                "items": [{"product_name": "Galateya", "type": "kit", "area": 12, "quantity": 1, "unit_price": "1250.00"}],
            },
        }
        first = self._post(payload)
        second = self._post(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(Deal.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ShopOrderImport.objects.count(), 1)
        self.assertEqual(Deal.objects.get().items.count(), 1)
        self.assertEqual(Deal.objects.get().funnel.name, "21 Основний продукт")

    def test_invalid_signature_is_rejected(self):
        response = self.client.post(
            "/api/integrations/shop/orders/", data=b"{}", content_type="application/json",
            HTTP_X_WALLCOV_TIMESTAMP=str(int(time.time())), HTTP_X_WALLCOV_SIGNATURE="wrong",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Deal.objects.count(), 0)

    def _post(self, payload):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b"test-shop-secret", timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/integrations/shop/orders/", data=raw, content_type="application/json",
            HTTP_X_WALLCOV_TIMESTAMP=timestamp, HTTP_X_WALLCOV_SIGNATURE=signature,
        )
