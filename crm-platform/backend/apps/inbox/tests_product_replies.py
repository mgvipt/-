"""Швидкі відповіді з номенклатури (17.09.2026): папка → відповіді, живі ціни, нова позиція → нова відповідь,
вимкнена сімʼя ховається; «тест-набір» і для підпапки «Викраски»."""
from decimal import Decimal
from types import SimpleNamespace

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.warehouse.models import Product, ProductCategory

from . import product_replies as PR
from .models import QuickReply, QuickReplyFolder


class ProductRepliesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.root = ProductCategory.objects.create(name="Тестові набори та викраски")
        self.samples = ProductCategory.objects.create(name="Викраски", parent=self.root)
        mk = lambda **kw: Product.objects.create(unit="шт", **kw)
        self.kits = [
            mk(name="Sirena Silk — тестовий набір (без дощечки без тонування)", price=Decimal("220"), category=self.root,
               shop_group_key="sample-sirena", shop_has_board=False, shop_is_tinted=False, shop_variant_order=1),
            mk(name="Sirena Silk — тестовий набір (з дощечкою та тонуванням)", price=Decimal("395"), category=self.root,
               shop_group_key="sample-sirena", shop_has_board=True, shop_is_tinted=True, shop_variant_order=4),
        ]
        self.sample = mk(name="Викраска 10×30 см · Sirena Silk — «Мокрий шовк»", price=Decimal("150"), category=self.samples)
        self.kit_link = QuickReplyFolder.objects.create(folder=self.root, category="Тест-набори з цінами", kind="test_set")
        self.s_link = QuickReplyFolder.objects.create(folder=self.samples, category="Викраски з цінами", kind="sample")

    def test_sync_creates_one_reply_per_family_with_live_prices(self):
        PR.sync_all(force=True)
        q = QuickReply.objects.get(product_folder=self.root)
        self.assertEqual(q.category, "Тест-набори з цінами")
        self.assertEqual(q.products.count(), 2)
        self.assertIn("{ціни}", q.text)
        txt = PR.render_text(q)
        self.assertIn("без дощечки, без тонування — 220 ₴", txt)
        self.assertIn("395 ₴", txt)
        Product.objects.filter(id=self.kits[0].id).update(price=Decimal("230"))
        self.assertIn("— 230 ₴", PR.render_text(QuickReply.objects.get(id=q.id)))   # ціна з номенклатури, без пересинхронізації
        s = QuickReply.objects.get(product_folder=self.samples)
        self.assertIn("150 ₴", PR.render_text(s))
        self.assertEqual(s.title, "Sirena Silk — «Мокрий шовк»")

    def test_new_product_adds_reply_and_disabled_family_hides(self):
        PR.sync_all(force=True)
        Product.objects.create(name="Викраска 10×30 см · Galateya", price=Decimal("150"), unit="шт", category=self.samples)
        PR.sync_all(force=True)
        self.assertEqual(QuickReply.objects.filter(product_folder=self.samples, is_active=True).count(), 2)
        Product.objects.filter(id=self.sample.id).update(is_active=False)
        PR.sync_all(force=True)
        q = QuickReply.objects.get(product_folder=self.samples, product_key="p%s" % self.sample.id)
        self.assertFalse(q.is_active)
        self.assertTrue(q.auto_hidden)
        Product.objects.filter(id=self.sample.id).update(is_active=True)
        PR.sync_all(force=True)
        self.assertTrue(QuickReply.objects.get(id=q.id).is_active)

    def test_manual_edits_are_kept(self):
        PR.sync_all(force=True)
        q = QuickReply.objects.get(product_folder=self.root)
        QuickReply.objects.filter(id=q.id).update(title="Мокрий шовк · тест-набір", text="Мій текст\n{ціни}")
        Product.objects.create(name="Sirena Silk — тестовий набір (з дощечкою без тонування)", price=Decimal("280"), unit="шт",
                               category=self.root, shop_group_key="sample-sirena", shop_has_board=True, shop_is_tinted=False)
        PR.sync_all(force=True)
        q.refresh_from_db()
        self.assertEqual(q.title, "Мокрий шовк · тест-набір")
        self.assertEqual(q.products.count(), 3)
        self.assertTrue(PR.render_text(q).startswith("Мій текст"))

    def test_api_picker_returns_rendered_prices(self):
        u = User.objects.create_user(username="mgr_qr", password="x")
        c = APIClient(); c.force_authenticate(u)
        r = c.get("/api/inbox/media-library/?view=picker")
        self.assertEqual(r.status_code, 200)
        kit = [x for x in r.data["replies"] if x["kind"] == "test_set"]
        self.assertEqual(len(kit), 1)
        self.assertNotIn("{ціни}", kit[0]["text"])
        self.assertEqual(kit[0]["price_range"], "220–395 ₴")
        self.assertEqual(len(kit[0]["products"]), 2)

    def test_samples_subfolder_still_counts_as_test_folder(self):
        from apps.crm.kit_tint import in_test_folder
        self.assertTrue(in_test_folder(Product.objects.select_related("category__parent").get(id=self.sample.id)))
        other = ProductCategory.objects.create(name="2.1. Фарби")
        self.assertFalse(in_test_folder(SimpleNamespace(category=other)))
