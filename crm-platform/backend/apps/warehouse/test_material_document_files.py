import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from .models import Product, InternalMaterialDocument
from .material_documents import ProductInternalDocumentFile, ProductInternalDocuments, private_document_path


class PrivateMaterialDocumentFileTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch("apps.warehouse.material_documents.PRIVATE_DOCUMENT_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.product = Product.objects.create(name="Private document test")
        self.other = Product.objects.create(name="Other material")
        self.pdf = b"%PDF-1.4\n%%EOF\n"
        self.sha = hashlib.sha256(self.pdf).hexdigest()
        (self.root / (self.sha + ".pdf")).write_bytes(self.pdf)
        self.doc = InternalMaterialDocument.objects.create(title_uk="Протокол", source_url="https://drive.google.com/file/d/abcdefghijklmnop123/view", content_sha256=self.sha, original_filename="original.pdf")
        self.doc.products.add(self.product)
        self.staff = get_user_model()(username="private-doc-staff", account_kind="staff", is_active=True, extra_permissions=["warehouse.view"])
        self.factory = APIRequestFactory()

    def response(self, user=None, product=None, doc=None):
        request = self.factory.get("/")
        if user is not None:
            force_authenticate(request, user=user)
        return ProductInternalDocumentFile.as_view()(request, pk=(product or self.product).pk, docid=(doc or self.doc).pk)

    def test_auth_permissions_and_active_staff(self):
        self.assertIn(self.response().status_code, (401, 403))
        denied = get_user_model()(username="noaccess", account_kind="staff", is_active=True, extra_permissions=[])
        self.assertEqual(self.response(denied).status_code, 403)
        self.staff.is_active = False
        self.assertEqual(self.response(self.staff).status_code, 403)
        client = get_user_model()(username="client", account_kind="client", is_active=True, is_superuser=True)
        self.assertEqual(self.response(client).status_code, 403)

    def test_authenticated_original_and_headers(self):
        response = self.response(self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.pdf)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertIn("no-store", response["Cache-Control"])
        response.close()

    def test_inbox_permission_and_m2m_share_one_file(self):
        inbox = get_user_model()(username="inbox", account_kind="staff", is_active=True, extra_permissions=["inbox.view"])
        self.doc.products.add(self.other)
        response = self.response(inbox, product=self.other)
        self.assertEqual(response.status_code, 200)
        response.close()
        second = InternalMaterialDocument.objects.create(title_uk="Same binary", source_url="https://drive.google.com/file/d/abcdefghijklmnop456/view", content_sha256=self.sha)
        second.products.add(self.other)
        self.assertEqual(private_document_path(second.content_sha256), private_document_path(self.doc.content_sha256))
        self.assertEqual(len(list(self.root.glob("*.pdf"))), 1)

    def test_unlinked_inactive_and_missing_files_404(self):
        self.assertEqual(self.response(self.staff, product=self.other).status_code, 404)
        self.doc.is_active = False
        self.doc.save()
        self.assertEqual(self.response(self.staff).status_code, 404)
        self.doc.is_active = True
        self.doc.save()
        (self.root / (self.sha + ".pdf")).unlink()
        self.assertEqual(self.response(self.staff).status_code, 404)

    def test_bad_hash_traversal_symlink_and_non_pdf_rejected(self):
        for value in ["../secret", "", "a" * 63, "A" * 64, "/etc/passwd", self.sha + ".pdf"]:
            self.assertIsNone(private_document_path(value))
        file = self.root / (self.sha + ".pdf")
        file.unlink()
        target = self.root / "other.pdf"
        target.write_bytes(self.pdf)
        file.symlink_to(target)
        self.assertEqual(self.response(self.staff).status_code, 404)
        file.unlink()
        file.write_text("not a PDF")
        self.assertEqual(self.response(self.staff).status_code, 404)

    def test_no_drive_url_when_local_file_available(self):
        request = self.factory.get("/")
        force_authenticate(request, user=self.staff)
        item = ProductInternalDocuments.as_view()(request, pk=self.product.pk).data["items"][0]
        self.assertEqual(item["url"], "")
        self.assertTrue(item["file_available"])
        self.assertNotIn("content_sha256", item)
        self.assertTrue(item["file_url"].endswith(f"/{self.doc.pk}/file/"))
