"""Run only on a test database after installing model + migration."""
from django.contrib.auth import get_user_model
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from .models import Product, InternalMaterialDocument
from .material_documents import ProductInternalDocuments
from .serializers import ProductSerializer


class InternalMaterialDocumentsTest(TestCase):
    url = "https://drive.google.com/file/d/abcdefghijklmnop123/view"

    def setUp(self):
        self.product = Product.objects.create(name="Document test")
        self.factory = APIRequestFactory()
        self.staff = get_user_model()(username="docstaff", account_kind="staff", is_active=True, extra_permissions=["warehouse.view"])

    def response(self, user=None, lang="uk"):
        request = self.factory.get("/", {"lang": lang})
        if user is not None:
            force_authenticate(request, user=user)
        return ProductInternalDocuments.as_view()(request, pk=self.product.pk)

    def document(self, **kwargs):
        return InternalMaterialDocument.objects.create(title_uk="Протокол", source_url=self.url, **kwargs)

    def test_anonymous_and_unprivileged_denied(self):
        self.assertIn(self.response().status_code, (401, 403))
        denied = get_user_model()(username="denied", account_kind="staff", is_active=True, extra_permissions=[])
        self.assertEqual(self.response(denied).status_code, 403)

    def test_inactive_denied_and_inbox_only_allowed(self):
        self.staff.is_active = False
        self.assertEqual(self.response(self.staff).status_code, 403)
        inbox = get_user_model()(username="inbox", account_kind="staff", is_active=True, extra_permissions=["inbox.view"])
        self.assertEqual(self.response(inbox).status_code, 200)
        client = get_user_model()(username="client", account_kind="client", is_active=True, is_superuser=True, extra_permissions=["inbox.view"])
        self.assertEqual(self.response(client).status_code, 403)

    def test_notes_language_and_no_download_contract(self):
        doc = self.document(notes_internal="Примітка", notes_ru="Примечание")
        doc.products.add(self.product)
        self.assertEqual(self.response(self.staff).data["items"][0]["notes"], "Примітка")
        item = self.response(self.staff, "ru").data["items"][0]
        self.assertEqual(item["notes"], "Примечание")
        self.assertNotIn("download_url", item)

    def test_normalization_and_canonical_unique_reference(self):
        doc = self.document()
        self.assertEqual(doc.source_key, "drive:abcdefghijklmnop123")
        with self.assertRaises(ValidationError):
            InternalMaterialDocument.objects.create(title_uk="Duplicate", source_url=self.url.replace("/view", "/preview") + "?usp=sharing")
        other = Product.objects.create(name="Other material")
        doc.products.add(self.product, other, self.product)
        self.assertEqual(doc.products.count(), 2)
        self.assertEqual(InternalMaterialDocument.objects.count(), 1)

    def test_unsafe_sources_rejected(self):
        for url in [self.url.replace("https:", "http:"), self.url.replace("drive.google.com", "drive.google.com.evil.test"), self.url.replace("drive.google.com", "user:password@drive.google.com"), self.url + "?token=secret", self.url + "#secret", self.url.replace("drive.google.com", "drive.google.com:443")]:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                InternalMaterialDocument.canonical_source(url)

    def test_linked_active_only_and_locale_archive_metadata(self):
        doc = self.document(title_ru="Протокол RU", is_archived=True, valid_until="2020-01-01")
        self.assertEqual(self.response(self.staff).data["items"], [])
        doc.products.add(self.product)
        response = self.response(self.staff, "ru")
        self.assertEqual(response.data["items"][0]["title"], "Протокол RU")
        self.assertTrue(response.data["items"][0]["is_archived"])
        self.assertIn("no-store", response["Cache-Control"])
        doc.is_active = False
        doc.save()
        self.assertEqual(self.response(self.staff).data["items"], [])

    def test_private_relation_not_in_product_serialization(self):
        doc = self.document()
        doc.products.add(self.product)
        payload = ProductSerializer(self.product).data
        self.assertNotIn("internal_documents", payload)
        self.assertNotIn("source_url", payload)
        self.assertNotIn(self.url, str(payload))
        self.assertNotIn("internal_documents", self.product.shop_specs or {})
