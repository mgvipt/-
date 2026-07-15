import hashlib
import hmac
import json
import time
import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.accounts.models import User
from apps.warehouse.models import Product
from .models import ShopOrderImport


@override_settings(SHOP_WEBHOOK_SECRET="test-shop-secret")
class ShopOrderWebhookTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        for name in ("21 Основний продукт", "22 Тестовий набір", "23 Інтернет-магазин"):
            funnel, _ = Funnel.objects.get_or_create(name=name)
            Stage.objects.get_or_create(funnel=funnel, order=0, defaults={"name": "Данні для розрахунку"})

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
        self.assertEqual(Deal.objects.get().funnel.name, "23 Інтернет-магазин")

    def test_sample_order_also_uses_only_shop_funnel(self):
        Product.objects.create(name="Galateya — повний тест-набір", sku="B24-38486", price=430, cost=180)
        payload = {
            "event_uuid": str(uuid.uuid4()),
            "order": {
                "number": "WV-SAMPLE-1", "customer_name": "Олег Тест", "phone": "+380501112233",
                "total": "399.00", "payment_method": "after_confirmation",
                "items": [{"sku": "B24-38486", "product_name": "Galateya — повний тест-набір", "type": "sample", "quantity": 1, "unit_price": "430.00"}],
            },
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, 201)
        deal = Deal.objects.get()
        self.assertEqual(deal.funnel.name, "23 Інтернет-магазин")
        self.assertEqual(deal.items.get().product.sku, "B24-38486")
        self.assertEqual(deal.items.get().custom_name, "")

    def test_unknown_sample_sku_is_rejected_before_deal_creation(self):
        payload = {
            "event_uuid": str(uuid.uuid4()),
            "order": {
                "number": "WV-SAMPLE-UNKNOWN", "customer_name": "Олег Тест", "phone": "+380501112233",
                "total": "399.00", "payment_method": "after_confirmation",
                "items": [{"sku": "WCV-NOT-IN-NOMENCLATURE", "product_name": "Вигаданий товар", "type": "sample", "quantity": 1, "unit_price": "399.00"}],
            },
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(Deal.objects.count(), 0)

    def test_manager_sees_unowned_first_stage_and_becomes_owner_after_moving_it(self):
        funnel = Funnel.objects.get(name="23 Інтернет-магазин")
        first_stage = funnel.stages.get(order=0)
        next_stage = Stage.objects.create(funnel=funnel, name="Розрахунок", order=1)
        manager = User.objects.create_user(
            username="shop-manager", password="test-pass", extra_permissions=["deal.stage.move"]
        )
        manager.extra_funnels.add(funnel)
        deal = Deal.objects.create(
            title="Сайт WV-QUEUE", funnel=funnel, stage=first_stage, source="site", amount=100
        )
        self.client.force_authenticate(manager)

        board = self.client.get(f"/api/deals/?funnel={funnel.id}")
        moved = self.client.patch(
            f"/api/deals/{deal.id}/", {"stage": next_stage.id}, format="json"
        )

        deal.refresh_from_db()
        self.assertEqual(board.status_code, 200)
        self.assertIn(deal.id, [row["id"] for row in board.json()["results"]])
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(deal.owner_id, manager.id)

    def test_checkout_name_replaces_only_generic_existing_contact_name(self):
        contact = Contact.objects.create(first_name="Гость", phone="+380501112233")
        Product.objects.create(name="Galateya — повний тест-набір", sku="B24-38486", price=430, cost=180)
        payload = {
            "event_uuid": str(uuid.uuid4()),
            "order": {
                "number": "WV-NAME-1", "customer_name": "Олег Тест", "phone": "+380501112233",
                "total": "399.00", "payment_method": "after_confirmation",
                "items": [{"sku": "B24-38486", "product_name": "Galateya — повний тест-набір", "type": "sample", "quantity": 1, "unit_price": "430.00"}],
            },
        }

        response = self._post(payload)

        contact.refresh_from_db()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(contact.first_name, "Олег")
        self.assertEqual(contact.last_name, "Тест")

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
