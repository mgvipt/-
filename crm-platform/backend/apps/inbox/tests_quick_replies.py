"""Швидкі відповіді (12.09): категорії й «коли використовувати»; незаповнені поля [сума] не йдуть клієнту."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.inbox.models import QuickReply
from apps.inbox.views import _unfilled_placeholder

HOST = "crm.wallcovdec.com.ua"


class QuickRepliesTests(TestCase):
    def test_unfilled_placeholder_detection(self):
        self.assertEqual(_unfilled_placeholder("Разом [сума] ₴ за [матеріал]"), "[сума]")
        self.assertEqual(_unfilled_placeholder("Ціна тест-набору [ціна тест-набору] ₴"), "[ціна тест-набору]")
        self.assertIsNone(_unfilled_placeholder("Олена, разом 6 200 ₴ за Мокрий шовк"))
        self.assertIsNone(_unfilled_placeholder("Відео [1/3] з нанесенням"))

    def test_picker_payload_has_category(self):
        QuickReply.objects.create(title="Дожим 1 · після розрахунку", text="{Ім'я}, добрий день!",
                                  category="Дожими і повернення з ігнору", when_to_use="Через 2 дні", sort=1000)
        admin = get_user_model().objects.create_superuser("qr-admin", "qr@example.test", "x")
        c = APIClient()
        c.force_authenticate(admin)
        r = c.get("/api/inbox/media-library/?view=picker", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        rep = [x for x in r.json()["replies"] if x["title"].startswith("Дожим 1")][0]
        self.assertEqual(rep["category"], "Дожими і повернення з ігнору")
        self.assertEqual(rep["when_to_use"], "Через 2 дні")
