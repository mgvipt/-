"""Контент-завод, етап 0: розбір посилань і доступ лише власнику. Без зовнішніх запитів."""
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from .models import ChannelLinkError, ContentChannel, parse_channel_link


class ParseLinkTests(SimpleTestCase):
    def test_profiles(self):
        cases = {
            "https://www.instagram.com/dekor_dlia_stin/": ("instagram", "dekor_dlia_stin"),
            "instagram.com/Textuuri?igsh=abc": ("instagram", "textuuri"),
            "https://www.tiktok.com/@Dekor_dlia_stin?lang=uk": ("tiktok", "dekor_dlia_stin"),
            "https://www.youtube.com/@Wallcov/shorts": ("youtube", "wallcov"),
            "https://youtube.com/channel/UC123abc": ("youtube", "channel/UC123abc"),
            "https://t.me/wallcovpro": ("telegram", "wallcovpro"),
            "t.me/s/wallcovpro": ("telegram", "wallcovpro"),
        }
        for link, (platform, handle) in cases.items():
            with self.subTest(link=link):
                p, h, _url = parse_channel_link(link)
                self.assertEqual((p, h), (platform, handle))

    def test_at_name_needs_platform(self):
        self.assertEqual(parse_channel_link("@wallcovpro", "telegram")[:2], ("telegram", "wallcovpro"))
        with self.assertRaises(ChannelLinkError):
            parse_channel_link("@wallcovpro")

    def test_posts_and_invites_rejected(self):
        for link in ("https://www.instagram.com/reel/DWLrZmljCcq/", "https://vm.tiktok.com/ZMabc/",
                     "https://youtu.be/abc", "https://www.youtube.com/watch?v=abc", "https://t.me/+AbCd",
                     "https://facebook.com/wallcov", ""):
            with self.subTest(link=link), self.assertRaises(ChannelLinkError):
                parse_channel_link(link)


class AccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="cf-owner", password="x", is_superuser=True, is_staff=True)
        self.manager = User.objects.create_user(username="cf-manager", password="x")
        self.trusted = User.objects.create_user(username="cf-trusted", password="x",
                                                extra_permissions=["content_factory.access"])

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_manager_forbidden(self):
        c = self._client(self.manager)
        self.assertEqual(c.get("/api/content-factory/channels/").status_code, 403)
        self.assertEqual(c.post("/api/content-factory/channels/", {"link": "t.me/x1"}, format="json").status_code, 403)
        self.assertFalse(ContentChannel.objects.exists())

    def test_trusted_with_permission_allowed(self):
        self.assertEqual(self._client(self.trusted).get("/api/content-factory/overview/").status_code, 200)

    def test_owner_add_duplicate_edit_delete(self):
        c = self._client(self.owner)
        r = c.post("/api/content-factory/channels/",
                   {"link": "https://www.instagram.com/dekor_dlia_stin/", "role": "own"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.json()["id"]
        dup = c.post("/api/content-factory/channels/", {"link": "instagram.com/DEKOR_DLIA_STIN"}, format="json")
        self.assertEqual(dup.status_code, 409)
        bad = c.post("/api/content-factory/channels/", {"link": "https://www.instagram.com/p/xyz/"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("пост", bad.json()["error"])
        r = c.patch(f"/api/content-factory/channels/{pk}/", {"note": "основний", "is_active": False}, format="json")
        self.assertEqual((r.json()["note"], r.json()["is_active"]), ("основний", False))
        ov = c.get("/api/content-factory/overview/").json()
        self.assertEqual(ov["channels_total"], 0)  # вимкнена не рахується
        self.assertEqual(c.delete(f"/api/content-factory/channels/{pk}/").status_code, 204)
