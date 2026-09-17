"""Публічні сторінки матеріалів і кольорів (17.09.2026): відкриваються без входу, показують лише активні файли."""
import secrets

from django.test import TestCase

from .models import MediaLibraryItem, SharedLink
from .showcase import slug_of


class ShowcaseTests(TestCase):
    def setUp(self):
        def item(**kw):
            f = SharedLink.objects.create(token=secrets.token_urlsafe(16), filename="x.jpg",
                                          content_type="image/jpeg", data=b"x")
            return MediaLibraryItem.objects.create(section="colors", file=f, **kw)
        self.swatch = item(title="Зразок Мокрий шовк", kind="image", material="Мокрий шовк", color_code="CSK 02-4", tags="зразок")
        self.inter = item(title="Вітальня · тепле світло", kind="image", material="Мокрий шовк", color_code="CSK 02-4", tags="інтерʼєр")
        self.video = item(title="Відео нанесення", kind="video", material="Мокрий шовк", color_code="CSK 02-4")
        item(title="Зразок Вельвет", kind="image", material="Вельвет Луна", color_code="SLK04-0,2", tags="зразок", is_active=False)

    def test_slugs(self):
        self.assertEqual(slug_of("Мокрий шовк"), "mokryi-shovk")
        self.assertEqual(slug_of("Вельвет Луна"), "velvet-luna")

    def test_pages_public_and_linked(self):
        r = self.client.get("/p/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Мокрий шовк", r.content.decode())
        self.assertNotIn("Вельвет Луна", r.content.decode())     # усі файли вимкнені — матеріалу немає
        r = self.client.get("/p/mokryi-shovk/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("CSK 02-4", html)
        self.assertIn("/p/mokryi-shovk/CSK+02-4/", html)
        self.assertIn("noindex", html)
        r = self.client.get("/p/mokryi-shovk/CSK+02-4/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("У інтерʼєрі", html)
        self.assertIn("<video", html)
        self.assertIn("Код кольору", html)

    def test_unknown_material_and_color(self):
        self.assertEqual(self.client.get("/p/nema-takogo/").status_code, 404)
        self.assertEqual(self.client.get("/p/mokryi-shovk/CSK+99-9/").status_code, 404)
