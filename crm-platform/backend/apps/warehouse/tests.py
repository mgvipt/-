from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from .models import Product, ProductCategory, ProductImage, ShopSyncEvent
from .shop_sync import catalog_validation_errors, infer_sample_metadata, prepare_product_for_shop, queue_product_sync


class ShopCatalogServiceTest(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(id=59, name="Тестові набори та викраски")

    def product(self, name="Travertino (без дощечки, без тонування)", **kwargs):
        data = dict(name=name, sku="SAMPLE-1", category=self.category, price=Decimal("490.00"))
        data.update(kwargs)
        return Product.objects.create(**data)

    def test_infers_four_sample_variants(self):
        names = [
            "Travertino (без дощечки, без тонування)",
            "Travertino (без дощечки, з тонуванням)",
            "Travertino (з дощечкою, без тонування)",
            "Travertino (з дощечкою, з тонуванням)",
        ]
        rows = [infer_sample_metadata(name) for name in names]
        self.assertEqual({row["shop_group_key"] for row in rows}, {rows[0]["shop_group_key"]})
        self.assertEqual([row["shop_variant_order"] for row in rows], [1, 2, 3, 4])

    def test_new_sample_stays_draft_and_creates_outbox(self):
        product = self.product()
        prepare_product_for_shop(product)
        event = queue_product_sync(product)
        product.refresh_from_db()
        self.assertTrue(product.shop_managed)
        self.assertEqual(product.shop_status, "draft")
        self.assertIn("Немає затвердженого фото", event.payload["product"]["validation_errors"])

    def test_publish_checklist_requires_price_and_approved_image(self):
        product = self.product(price=0)
        prepare_product_for_shop(product)
        self.assertIn("Ціна повинна бути більшою за 0", catalog_validation_errors(product))
        product.price = 490
        product.save(update_fields=["price"])
        ProductImage.objects.create(product=product, file_path="/tmp/photo.jpg", is_approved=True)
        self.assertEqual(catalog_validation_errors(product), [])

    def test_manual_boolean_choice_is_not_overwritten(self):
        product = self.product(shop_group_key="manual", shop_variant_order=4,
                               shop_has_board=False, shop_is_tinted=False)
        prepare_product_for_shop(product)
        self.assertFalse(product.shop_has_board)
        self.assertFalse(product.shop_is_tinted)

    def test_new_event_supersedes_old_failed_payload(self):
        product = self.product()
        old = queue_product_sync(product)
        old.status = "failed"; old.save(update_fields=["status"])
        current = queue_product_sync(product)
        old.refresh_from_db()
        self.assertEqual(old.status, "superseded")
        self.assertEqual(current.status, "pending")

    @override_settings(SHOP_WEBHOOK_SECRET="test-secret")
    @patch("apps.warehouse.shop_sync.urllib.request.urlopen")
    def test_delivery_is_signed_and_marks_processed(self, urlopen):
        product = self.product()
        event = queue_product_sync(product)
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"status":"draft","url":"https://wallcov.com.ua/new/product/test"}'
        from .shop_sync import deliver_event
        deliver_event(event)
        event.refresh_from_db(); product.refresh_from_db()
        self.assertEqual(event.status, "processed")
        self.assertEqual(product.shop_status, "draft")
        sent = urlopen.call_args.args[0]
        self.assertTrue(sent.get_header("X-wallcov-signature"))

    @override_settings(SHOP_WEBHOOK_SECRET="test-secret")
    @patch("apps.warehouse.shop_sync.urllib.request.urlopen")
    def test_delivery_updates_status_for_every_variant_in_group(self, urlopen):
        first = self.product(shop_group_key="sample-group", shop_status="ready", shop_managed=True)
        second = self.product(name="Travertino (з дощечкою, з тонуванням)",
                              sku="SAMPLE-2", shop_group_key="sample-group", shop_status="ready", shop_managed=True)
        event = queue_product_sync(first)
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"status":"published","url":"https://wallcov.com.ua/new/product/travertino"}'
        from .shop_sync import deliver_event
        deliver_event(event)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(first.shop_status, "published")
        self.assertEqual(second.shop_status, "published")
