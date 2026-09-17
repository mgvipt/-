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
        self.assertIn("Обрати цей колір", html)      # кнопка: код іде менеджеру в чат
        self.assertIn('id="lb"', html)               # фото відкривається в цьому ж вікні
        self.assertIn("✕ Закрити", html)
        self.assertIn("data-full=", html)
        self.assertNotIn('target="_blank"', html.split('class="pick"')[0])   # фото — без нової вкладки
        self.assertIn("wa.me/380973282283", html)
        self.assertIn("msng.link/o?380973282283=vi", html)   # робочий лінк Viber

    def test_unknown_material_and_color(self):
        self.assertEqual(self.client.get("/p/nema-takogo/").status_code, 404)
        self.assertEqual(self.client.get("/p/mokryi-shovk/CSK+99-9/").status_code, 404)


class ShowcasePickTests(TestCase):
    """Кнопка «Обрати цей колір» на персональному посиланні пише у той самий чат CRM (17.09.2026)."""

    def setUp(self):
        from apps.inbox.models import Channel, Conversation
        ch = Channel.objects.create(kind="instagram", name="IG")
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="chat-1", title="Клієнт")

    def test_link_and_pick_writes_into_conversation(self):
        from apps.inbox import showcase
        from apps.inbox.models import Message
        link = showcase.page_link("velvet-luna", "SLK03-10", self.conv.id)
        self.assertIn("/p/velvet-luna/SLK03-10/?c=", link)
        token = link.split("?c=", 1)[1]
        r = self.client.post("/p/pick/", {"c": token, "text": "Обрав колір Вельвет Луна · SLK03-10"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        m = Message.objects.get(conversation=self.conv)
        self.assertEqual(m.direction, "in")
        self.assertIn("SLK03-10", m.text)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.unread, 1)

    def test_bad_token_rejected(self):
        r = self.client.post("/p/pick/", {"c": "щось-не-те", "text": "х"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_placeholder_in_outgoing_text(self):
        from apps.inbox import showcase
        out = showcase.personalize("Ось кольори: {кольори:velvet-luna}", self.conv)
        self.assertIn("https://wallcov.com.ua/p/velvet-luna/?c=", out)
        self.assertEqual(showcase.personalize("без плейсхолдера", self.conv), "без плейсхолдера")


class PayLinkNotBrokenTests(TestCase):
    """18.09.2026: сторінки /p/<матеріал>/ не повинні перехоплювати ПОСИЛАННЯ НА ОПЛАТУ /p/<код>/."""

    def test_paylink_still_works(self):
        from apps.crm.models import Deal, Funnel, PayLink, Stage
        f = Funnel.objects.create(name="22 Тестовий набір")
        st = Stage.objects.create(funnel=f, name="Домовились про оплату", order=2)
        d = Deal.objects.create(title="T", funnel=f, stage=st)
        PayLink.objects.create(code="YwOhyDY", deal=d, target="https://www.liqpay.ua/api/3/checkout?data=x")
        r = self.client.get("/p/YwOhyDY/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("liqpay", r["Location"])
        self.assertEqual(self.client.get("/p/nemaje-takogo-kodu/").status_code, 404)
