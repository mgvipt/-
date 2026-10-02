"""Campaign workflow in an isolated database; no provider calls."""
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.inbox.models import SharedLink
from apps.warehouse.models import Product
from .models import Blog, CampaignMaterial, Carousel, ContentCampaign, ReelDraft, TgPost, SourceAsset, VideoScene
from .campaigns import campaign_data, material_data, require_current_approval, snapshot

BASE = "/api/content-factory/campaigns/"


class CampaignTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="campaign-owner", is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.blog, _ = Blog.objects.get_or_create(slug="wallcov", defaults={"name": "Wallcov"})
        self.product = Product.objects.create(name="Campaign test product", price="120", unit="кг")
        self.c = ContentCampaign.objects.create(title="Test", goal="Заявки", audience="Дизайнеры", blog=self.blog,
                                                 product=self.product, product_snapshot=snapshot(self.product))

    def material(self, kind="post"):
        if kind == "post":
            obj = TgPost.objects.create(title="Post", text="Проверенный текст")
        elif kind == "carousel":
            obj = Carousel.objects.create(title="Carousel", blog=self.blog, slides=[{"rendered_id": 1}])
        else:
            media = SharedLink.objects.create(token="campaign-test", filename="test.mp4", data=b"test")
            asset = SourceAsset.objects.create(origin="drive", kind="video", file_name="test.mp4")
            scene = VideoScene.objects.create(asset=asset, start=0, end=3, what="Тестовый кадр")
            obj = ReelDraft.objects.create(title="Reel", blog=self.blog, file=media, beats=[{"scene_id": scene.id, "text": "фраза", "seconds": 3}])
        return CampaignMaterial.objects.create(campaign=self.c, **{kind: obj})

    def approve(self, item, **overrides):
        body = {"version": material_data(item)["version"], "checks": {"facts": True, "visual": True, "rights": True}}
        body.update(overrides)
        return self.client.post(f"{BASE}{self.c.id}/materials/{item.id}/", body, format="json")

    def test_create_and_persist_product_snapshot(self):
        r = self.client.post(BASE, {"title": "Galatea", "goal": "Заявки", "audience": "Дизайнеры", "blog_id": self.blog.id,
                                   "product_id": self.product.id, "budget_usd": "25.50"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        result = self.client.get(f"{BASE}{r.data['id']}/").data
        self.assertEqual(result["product_snapshot"]["product"]["price"], "120.00")
        self.assertEqual(result["total"], 0)

    def test_access_checks_every_endpoint(self):
        user = User.objects.create_user(username="campaign-manager")
        self.client.force_authenticate(user)
        for url in [BASE, BASE+"choices/", f"{BASE}{self.c.id}/", f"{BASE}{self.c.id}/materials/", f"{BASE}{self.c.id}/materials/1/"]:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}, format="json").status_code, 403)

    def test_invalid_dates_budget_and_product(self):
        data = {"title": "X", "goal": "Y", "audience": "Z", "blog_id": self.blog.id, "product_id": self.product.id}
        for extra in [{"budget_usd": -1}, {"starts_on": "2026-10-10", "ends_on": "2026-10-01"}, {"product_id": 999999}]:
            self.assertEqual(self.client.post(BASE, {**data, **extra}, format="json").status_code, 400)

    def test_stale_campaign_update_rejected(self):
        url = f"{BASE}{self.c.id}/"
        self.assertEqual(self.client.patch(url, {"revision": 1, "goal": "Новая цель"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"revision": 1, "goal": "Старая цель"}, format="json").status_code, 409)
        self.c.refresh_from_db()
        self.assertEqual(self.c.goal, "Новая цель")

    def test_create_draft_and_attach_without_generation(self):
        with patch("apps.content_factory.studio.build_script") as generate:
            r = self.client.post(f"{BASE}{self.c.id}/materials/", {"kind": "reel", "title": "Макро фактуры"}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(r.data["state"], "planned")
            self.assertTrue(r.data["issues"])
            generate.assert_not_called()
        other = ContentCampaign.objects.create(title="Other", goal="Y", audience="Z", blog=self.blog,
                                               product=self.product, product_snapshot=snapshot(self.product))
        duplicate = self.client.post(f"{BASE}{other.id}/materials/", {"kind": "reel", "target_id": r.data["target_id"]}, format="json")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(ReelDraft.objects.count(), 1)

    def test_cross_blog_attachment_forbidden(self):
        blog = Blog.objects.create(name="Other", slug="campaign-other")
        reel = ReelDraft.objects.create(title="Other", blog=blog)
        r = self.client.post(f"{BASE}{self.c.id}/materials/", {"kind": "reel", "target_id": reel.id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_version_and_all_checks_required(self):
        item = self.material()
        self.assertEqual(self.approve(item, version="old").status_code, 409)
        self.assertEqual(self.approve(item, checks={"facts": True}).status_code, 400)
        self.assertEqual(self.approve(item).status_code, 200)
        item.post.refresh_from_db()
        self.assertEqual(item.post.status, "draft")  # review never schedules/publishes
        require_current_approval(item.post)

    def test_edit_invalidates_review_and_publisher_blocks_before_network(self):
        from . import telegram
        item = self.material()
        self.assertEqual(self.approve(item).status_code, 200)
        item.post.text = "Другая фраза"
        item.post.status = "approved"
        item.post.save()
        item.refresh_from_db()
        self.assertEqual(material_data(item)["state"], "changed")
        with patch.object(telegram, "tg_config", return_value=("", "test", "")), patch.object(telegram, "send") as send:
            with self.assertRaises(telegram.PublishError):
                telegram.publish(item.post_id)
            send.assert_not_called()

    def test_reel_voice_or_frame_edit_invalidates(self):
        item = self.material("reel")
        self.assertEqual(self.approve(item).status_code, 200)
        item.reel.brief = {"narration": "Новая озвучка"}
        item.reel.save()
        with self.assertRaises(ValueError):
            require_current_approval(item.reel)
        from .publish import publish_reel, PublishError
        with patch("apps.content_factory.publish._ig") as provider:
            with self.assertRaises(PublishError):
                publish_reel(item.reel, "instagram")
            provider.assert_not_called()

    def test_carousel_edit_blocks_publication(self):
        item = self.material("carousel")
        self.assertEqual(self.approve(item).status_code, 200)
        item.carousel.caption = "Изменение"
        item.carousel.save()
        from .publish import publish_carousel, PublishError
        with self.assertRaises(PublishError):
            publish_carousel(item.carousel)

    def test_missing_scene_cannot_be_approved(self):
        item = self.material("reel")
        VideoScene.objects.filter(pk=item.reel.beats[0]["scene_id"]).delete()
        self.assertEqual(self.approve(item).status_code, 400)

    def test_product_change_blocks_until_refresh_and_review(self):
        item = self.material()
        self.assertEqual(self.approve(item).status_code, 200)
        self.product.price = 140
        self.product.save()
        with self.assertRaises(ValueError):
            require_current_approval(item.post)
        r = self.client.patch(f"{BASE}{self.c.id}/", {"revision": 1, "refresh_product": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["product_changed"])
        self.assertEqual(r.data["materials"][0]["state"], "changed")

    def test_archiving_blocks_and_legacy_materials_unchanged(self):
        item = self.material()
        self.assertEqual(self.approve(item).status_code, 200)
        self.c.archived = True
        self.c.save()
        with self.assertRaises(ValueError):
            require_current_approval(item.post)
        legacy = TgPost.objects.create(title="Legacy", text="Existing")
        require_current_approval(legacy)

    def test_plan_date_is_not_publication_schedule(self):
        item = self.material()
        r = self.client.patch(f"{BASE}{self.c.id}/materials/{item.id}/", {"planned_on": "2026-10-05", "note": "Нужен крупный план"}, format="json")
        self.assertEqual(r.status_code, 200)
        item.post.refresh_from_db()
        self.assertIsNone(item.post.scheduled_at)

    def test_exactly_one_target_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampaignMaterial.objects.create(campaign=self.c)

    def test_published_state_is_derived_from_saved_publication(self):
        item = self.material()
        item.post.status = "published"
        item.post.tg_message_id = "123"
        item.post.save()
        data = campaign_data(self.c)
        self.assertEqual(data["state"], "Завершена")
        self.assertEqual(data["materials"][0]["published"]["telegram"]["id"], "123")
