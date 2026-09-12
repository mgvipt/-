"""Прийом заявок з кількох сайтів (12.09.2026): wallcovdliastin як раніше, dekoratyvna — своя воронка,
магазин wallcov.com.ua — підписаний запит у воронку 23. Тільки ізольована тестова БД."""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import Department, Role, User
from apps.crm.models import Deal, Funnel, Stage, Task
from .models import Conversation, LandingSubmission, Message

SECRET = "test-only-secret"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
LEGACY = "https://wallcovdliastin.com.ua"
DEKOR = "https://dekoratyvna-shtukaturka.com.ua"
SHOP_URL = "/api/integrations/shop/leads/"


def _signed(client, payload, secret=SECRET, ts=None):
    body = json.dumps(payload, ensure_ascii=False).encode()
    ts = str(ts or int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return client.post(SHOP_URL, data=body, content_type="application/json",
                       HTTP_X_WALLCOV_TIMESTAMP=ts, HTTP_X_WALLCOV_SIGNATURE=sig)


@override_settings(CACHES=LOCMEM, SHOP_WEBHOOK_SECRET=SECRET)
class SiteLeadTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(username="test-queue-admin", is_superuser=True)
        self.legacy = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua")
        Stage.objects.create(funnel=self.legacy, name="Новая заявка", order=0)
        self.dekor = Funnel.objects.create(name="Лендинг · dekoratyvna-shtukaturka.com.ua")
        Stage.objects.create(funnel=self.dekor, name="Новая заявка", order=0)
        self.shop = Funnel.objects.create(name="23 Інтернет-магазин wallcov.com.ua")
        Stage.objects.create(funnel=self.shop, name="Нове замовлення з сайту", order=0)
        self.shop_payload = {
            "submission_id": "a1b2c3d4e5f6", "form": "article_calc", "article": "yak-nanesty-mokryi-shovk",
            "page_url": "https://wallcov.com.ua/porady/yak-nanesty-mokryi-shovk", "name": "Олена",
            "phone": "+380970000031", "consent": True, "preferred": "viber", "area": 18,
            "product": "mokryi-shovk", "product_label": "Мокрий шовк", "message": "Скільки треба на кімнату?",
            "first_touch": {"utm_source": "google", "gclid": "test-gclid"},
            "last_touch": {"referrer": "https://wallcov.com.ua/"},
        }

    def _web(self, payload, origin):
        return self.client.post("/api/inbox/web-chat/", data=payload, content_type="application/json", HTTP_ORIGIN=origin)

    def _start(self, origin, visitor="visitor-1"):
        response = self._web({"action": "start", "visitor_id": visitor}, origin)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_dekoratyvna_lead_goes_to_its_own_funnel(self):
        started = self._start(DEKOR)
        conv = Conversation.objects.get(pk=started["conversation_id"])
        self.assertTrue(conv.external_chat_id.startswith("dekoratyvna-shtukaturka.com.ua:"))
        self.assertIn("декоративне покриття", conv.messages.get().text)
        lead = self._web({"action": "lead", "token": started["token"], "name": "Тест", "phone": "0970000021",
                          "consent": True, "product": "Travertino", "product_label": "Травертин", "area": 25,
                          "room": "Вітальня", "message": "Хочу як на фото", "preferred": "whatsapp",
                          "submission_id": "dekor-test-1", "first_touch": {"utm_source": "google", "utm_medium": "organic"}},
                         DEKOR)
        self.assertEqual(lead.status_code, 200, lead.content)
        deal = Deal.objects.get(pk=lead.json()["deal_id"])
        self.assertEqual(deal.funnel, self.dekor)
        q = deal.qualification
        self.assertEqual(q["landing_id"], "dekoratyvna-shtukaturka.com.ua")
        self.assertEqual((q["product"], q["product_key"]), ("Травертин", "travertino"))
        self.assertEqual(q["preferred_channel"], "whatsapp")
        self.assertEqual(q["utm"]["utm_source"], "google")
        self.assertEqual(q["estimate_kind"], "needs_consultation")
        self.assertEqual(deal.amount, Decimal("0"))
        self.assertIsNone(lead.json()["minimum_order"])
        self.assertIn("dekoratyvna-shtukaturka.com.ua", Task.objects.get(deal=deal).title)
        self.assertIn("Хочу як на фото", Message.objects.get(conversation=conv, internal=True).text)
        conv.refresh_from_db()
        self.assertTrue(conv.title.startswith("[dekoratyvna-shtukaturka.com.ua]"))

    def test_wallcovdliastin_is_unchanged(self):
        started = self._start(LEGACY)
        lead = self._web({"action": "lead", "token": started["token"], "name": "Тест", "phone": "0970000012",
                          "consent": True, "room": "Спальня", "area": 30, "product": "sirena",
                          "preferred": "whatsapp", "submission_id": "legacy-test-1"}, LEGACY)
        self.assertEqual(lead.status_code, 200, lead.content)
        deal = Deal.objects.get(pk=lead.json()["deal_id"])
        self.assertEqual(deal.funnel, self.legacy)
        self.assertEqual(deal.amount, Decimal("5692.50"))
        self.assertEqual(lead.json()["minimum_order"], 220)
        self.assertEqual(deal.qualification["landing_id"], "wallcovdliastin.com.ua")
        self.assertEqual(deal.qualification["preferred_channel"], "phone")  # whatsapp тут як і раніше не приймається
        self.assertNotIn("article", deal.qualification)
        self.assertEqual(Task.objects.get(deal=deal).title, "Прийняти звернення з сайту #%s" % deal.id)
        conv = Conversation.objects.get(pk=started["conversation_id"])
        self.assertTrue(conv.title.startswith("[wallcovdliastin.com.ua]"))
        self.assertTrue(conv.messages.filter(external_id__startswith="web-contact:").exists())

    def test_token_of_one_site_is_rejected_on_another(self):
        started = self._start(DEKOR)
        self.assertEqual(self._web({"action": "poll", "token": started["token"]}, LEGACY).status_code, 401)
        self.assertEqual(self._web({"action": "poll", "token": started["token"]}, DEKOR).status_code, 200)

    def test_landing_id_in_body_cannot_override_origin(self):
        response = self._web({"action": "start", "visitor_id": "x", "landing_id": "wallcovdliastin.com.ua"}, DEKOR)
        self.assertEqual(response.status_code, 400)
        response = self._web({"action": "start", "visitor_id": "x", "landing_id": "wallcov.com.ua"}, DEKOR)
        self.assertEqual(response.status_code, 400)

    def test_honeypot_blocks_lead(self):
        started = self._start(DEKOR)
        response = self._web({"action": "lead", "token": started["token"], "phone": "0970000021", "consent": True,
                              "submission_id": "spam-test-1", "website": "http://spam.example"}, DEKOR)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Deal.objects.count(), 0)

    def test_shop_signed_lead_goes_to_shop_funnel_with_article(self):
        response = _signed(self.client, self.shop_payload)
        self.assertEqual(response.status_code, 201, response.content)
        deal = Deal.objects.get(pk=response.json()["deal_id"])
        self.assertEqual(deal.funnel, self.shop)
        q = deal.qualification
        self.assertEqual(q["landing_id"], "wallcov.com.ua")
        self.assertEqual(q["article"], "yak-nanesty-mokryi-shovk")
        self.assertEqual(q["form"], "article_calc")
        self.assertEqual(q["attribution"]["first_touch"]["gclid"], "test-gclid")
        self.assertEqual(q["attribution"]["last_touch"]["referrer"], "https://wallcov.com.ua/")
        self.assertEqual(q["product"], "Мокрий шовк")
        conv = Conversation.objects.get(pk=q["conversation_id"])
        self.assertEqual(conv.channel.kind, "web")
        self.assertEqual(conv.external_chat_id, "wallcov.com.ua:form:a1b2c3d4e5f6")
        self.assertFalse(conv.messages.filter(internal=False).exists())  # клієнту нічого не пишемо
        self.assertIn("yak-nanesty-mokryi-shovk", conv.messages.get(internal=True).text)
        retry = _signed(self.client, self.shop_payload)
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.json()["duplicate"])
        self.assertEqual(retry.json()["deal_id"], deal.id)
        self.assertEqual((Deal.objects.count(), Conversation.objects.count(), Task.objects.count()), (1, 1, 1))
        changed = _signed(self.client, {**self.shop_payload, "area": 40})
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json()["code"], "conflict")

    def test_shop_lead_requires_signature_consent_and_valid_id(self):
        body = json.dumps(self.shop_payload)
        self.assertEqual(self.client.post(SHOP_URL, data=body, content_type="application/json").status_code, 403)
        self.assertEqual(_signed(self.client, self.shop_payload, secret="wrong").status_code, 403)
        self.assertEqual(_signed(self.client, self.shop_payload, ts=int(time.time()) - 900).status_code, 403)
        no_consent = _signed(self.client, {**self.shop_payload, "consent": False})
        self.assertEqual(no_consent.status_code, 400)
        bad_id = _signed(self.client, {**self.shop_payload, "submission_id": "short"})
        self.assertEqual((bad_id.status_code, bad_id.json()["field"]), (400, "submission_id"))
        bad_phone = _signed(self.client, {**self.shop_payload, "phone": "123"})
        self.assertEqual(bad_phone.status_code, 400)
        self.assertEqual((Deal.objects.count(), Conversation.objects.count(), LandingSubmission.objects.count()), (0, 0, 0))

    def test_shop_quiz_answers_are_kept(self):
        payload = {**self.shop_payload, "submission_id": "quiz-000001", "form": "quiz", "article": "quiz",
                   "quiz": {"Кімната": "Спальня", "Ефект": ["Шовк", "Перламутр"]}}
        response = _signed(self.client, payload)
        self.assertEqual(response.status_code, 201, response.content)
        q = Deal.objects.get(pk=response.json()["deal_id"]).qualification
        self.assertEqual(q["quiz"], {"Кімната": "Спальня", "Ефект": "Шовк, Перламутр"})
        self.assertEqual(q["article"], "quiz")


class EnsureLandingFunnelTests(TestCase):
    def test_dry_run_then_apply_copies_stages_department_and_visibility(self):
        template = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua", order=14)
        names = ["Новая заявка", "Первый контакт", "Сделка успешна", "Не реализовано"]
        stages = [Stage.objects.create(funnel=template, name=n, order=i, color="#ef4444",
                                       is_won=(n == "Сделка успешна"), is_lost=(n == "Не реализовано"))
                  for i, n in enumerate(names)]
        dept = Department.objects.create(name="Відділ продажів (тест)")
        dept.funnels.add(template)
        role = Role.objects.create(name="Менеджер (тест)", stage_view_all=[s.id for s in stages])
        user = User.objects.create_user(username="extra-funnel-test")
        user.extra_funnels.add(template)

        out = StringIO()
        call_command("ensure_landing_funnels", stdout=out)
        self.assertIn("DRY", out.getvalue())
        self.assertFalse(Funnel.objects.filter(name__contains="dekoratyvna").exists())

        call_command("ensure_landing_funnels", "--apply", stdout=StringIO())
        new = Funnel.objects.get(name="Лендинг · dekoratyvna-shtukaturka.com.ua")
        fields = ("name", "order", "color", "is_won", "is_lost", "auto_only")
        self.assertEqual(list(new.stages.order_by("order").values_list(*fields)),
                         list(template.stages.order_by("order").values_list(*fields)))
        self.assertTrue(dept.funnels.filter(pk=new.pk).exists())
        self.assertTrue(user.extra_funnels.filter(pk=new.pk).exists())
        role.refresh_from_db()
        self.assertTrue(set(new.stages.values_list("id", flat=True)) <= set(role.stage_view_all))

        call_command("ensure_landing_funnels", "--apply", stdout=StringIO())  # повтор нічого не дублює
        self.assertEqual(Funnel.objects.filter(name=new.name).count(), 1)
        self.assertEqual(new.stages.count(), 4)
        role.refresh_from_db()
        self.assertEqual(len(role.stage_view_all), 8)
