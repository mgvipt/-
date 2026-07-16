from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIClient

from .models import Product, ShopCatalogImportBatch
from .shop_sync import prepare_regular_product_for_shop


class ShopCatalogImportTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="shop-admin", password="test")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.product = Product.objects.create(name="Velvet Lux", sku="B24-38417", bitrix_id=38417, price=900)

    def workbook(self, reversed_range=False):
        workbook = Workbook()
        material = workbook.active
        material.title = "Материалы"
        material.append([
            "ID / SKU", "Клиентское название", "Короткое описание для клиента", "Эффект / ассоциация",
            "Где использовать", "Можно наносить самому?", "Цена: модель", "Цена за кг, грн",
            "Расход min, кг/м²", "Расход max, кг/м²", "Расчётная цена min, грн/м²",
            "Расчётная цена max, грн/м²", "Финиш", "Можно мыть?", "Износостойкость",
        ])
        minimum, maximum = (0.7, 0.1) if reversed_range else (0.35, 0.6)
        material.append([38417, "Мягкий шёлк", "Описание", "Шёлк", "Спальня, Гостиная", "Да", "за кг", 1012, minimum, maximum, 1012 * minimum, 1012 * maximum, "Матовый", "Да", "Высокая"])
        samples = workbook.create_sheet("Тест-наборы")
        samples.append(["ID материала", "Внутреннее название набора", "Клиентское название набора", "Когда предлагать", "Что входит", "Цена, грн"])
        output = BytesIO()
        workbook.save(output)
        return SimpleUploadedFile("catalog.xlsx", output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_upload_creates_review_without_changing_product(self):
        response = self.client.post("/api/shop-import/upload/", {"file": self.workbook()}, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "900.00")
        self.assertEqual(response.data["summary"]["rows"], 1)
        self.assertEqual(response.data["summary"]["price_changes"], 1)

    def test_reversed_consumption_blocks_apply_until_corrected(self):
        response = self.client.post("/api/shop-import/upload/", {"file": self.workbook(reversed_range=True)}, format="multipart")
        row = response.data["rows"][0]
        self.assertTrue(row["errors"])
        batch = ShopCatalogImportBatch.objects.get(pk=response.data["id"])
        apply_response = self.client.post(f"/api/shop-import/batches/{batch.id}/apply/", {"confirm": True, "row_ids": [row["id"]]}, format="json")
        self.assertEqual(apply_response.status_code, 400)

    def test_confirmed_apply_updates_same_crm_product_but_does_not_publish(self):
        response = self.client.post("/api/shop-import/upload/", {"file": self.workbook()}, format="multipart")
        row = response.data["rows"][0]
        batch_id = response.data["id"]
        apply_response = self.client.post(f"/api/shop-import/batches/{batch_id}/apply/", {"confirm": True, "row_ids": [row["id"]]}, format="json")
        self.assertEqual(apply_response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "1012.00")
        self.assertEqual(self.product.shop_parent_name, "Мягкий шёлк")
        self.assertEqual(self.product.shop_specs["consumption_min"], 0.35)
        self.assertFalse(self.product.shop_enabled)

    def test_apply_requires_explicit_confirmation(self):
        response = self.client.post("/api/shop-import/upload/", {"file": self.workbook()}, format="multipart")
        row = response.data["rows"][0]
        apply_response = self.client.post(f"/api/shop-import/batches/{response.data['id']}/apply/", {"row_ids": [row["id"]]}, format="json")
        self.assertEqual(apply_response.status_code, 400)

    def test_regular_product_gets_technical_group_and_url_automatically(self):
        self.product.shop_variant_type = "product"
        self.product.shop_group_key = ""
        self.product.shop_slug = ""
        self.product.shop_parent_name = ""
        self.product.save()
        prepare_regular_product_for_shop(self.product)
        self.product.refresh_from_db()
        self.assertEqual(self.product.shop_group_key, f"product-{self.product.id}")
        self.assertEqual(self.product.shop_slug, f"product-{self.product.id}")
        self.assertEqual(self.product.shop_parent_name, self.product.name)
