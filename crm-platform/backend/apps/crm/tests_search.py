"""Пошук по CRM (15.09.2026, chatsearch): розбір рядка + глобальний пошук у шапці (/api/search/).

Олег: «за іменем не знаходжу і за нікнеймом теж не шукає» — приклад «Івана Забурко» (FB-коментар).
"""
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.crm.search_text import parse_query, phone_core, term_variants
from apps.inbox.models import Channel, Conversation


class ParseQueryTests(SimpleTestCase):
    def test_multi_word_any_spacing(self):
        self.assertEqual(parse_query("  Івана   Забурко ").terms, ["Івана", "Забурко"])

    def test_nick_and_profile_link(self):
        self.assertEqual(parse_query("@daria_atanova66").terms, ["daria_atanova66"])
        self.assertEqual(parse_query("https://instagram.com/malik.o.svetlana?igsh=abc").terms, ["malik.o.svetlana"])
        self.assertEqual(parse_query("https://www.tiktok.com/@user.name/").terms, ["user.name"])

    def test_phone_formats_same_core(self):
        for raw in ("+380638682204", "380638682204", "0638682204", "063 868 22 04", "+38 (063) 868-22-04", "80638682204"):
            p = parse_query(raw)
            self.assertEqual(p.phone, "638682204", raw)
            self.assertEqual(p.terms, [])

    def test_apostrophes_normalized(self):
        for raw in ("Мар'яна", "Марʼяна", "Мар’яна", "Мар`яна"):
            self.assertEqual(parse_query(raw).terms, ["Мар'яна"], raw)
        v = term_variants("Мар'яна")
        for a in ("Мар'яна", "Марʼяна", "Мар’яна"):
            self.assertIn(a, v)

    def test_translit_both_ways(self):
        self.assertIn("івана", term_variants("Ivana"))
        self.assertIn("ивана", term_variants("Ivana"))
        self.assertIn("zaburko", term_variants("Забурко"))
        self.assertIn("дарія", term_variants("Daria"))
        self.assertIn("марія", term_variants("Mariia"))
        self.assertEqual(term_variants("daria_atanova66"), ["daria_atanova66"])  # нік — без вигадок

    def test_initials_dropped_and_empty(self):
        self.assertEqual(parse_query("І. Забурко").terms, ["Забурко"])
        self.assertIsNone(parse_query("   "))
        self.assertIsNone(parse_query("@"))

    def test_phone_core(self):
        self.assertEqual(phone_core("380671234567"), "671234567")
        self.assertEqual(phone_core("0671234567"), "671234567")
        self.assertEqual(phone_core("12345"), "12345")


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.funnel = Funnel.objects.create(name="Основна (тест)")
        self.stage = Stage.objects.create(funnel=self.funnel, name="Новий", order=0)
        self.owner = User.objects.create_superuser("chs-owner", password="x")
        self.laptev = User.objects.create_user("chs-laptev", password="x", first_name="Олександр")
        role = Role.objects.create(name="Менеджер (пошук тест)", permissions=["inbox.view"])
        self.mgr = User.objects.create_user("chs-mgr", password="x", role=role)
        self.no_inbox = User.objects.create_user("chs-noinbox", password="x",
                                                 role=Role.objects.create(name="Без чатів (тест)", permissions=[]))
        self.ch = Channel.objects.create(kind="telegram", name="TG тест")
        self.ivana = Contact.objects.create(first_name="Івана", last_name="Забурко", owner=self.laptev)
        self.maryana = Contact.objects.create(first_name="Марʼяна", last_name="Коваль", phone="+38 (063) 868-22-04")
        self.daria = Contact.objects.create(first_name="Stepanova", last_name="Daria", nickname="daria_atanova66",
                                            social_link="https://instagram.com/daria_atanova66")
        self.pavlo = Contact.objects.create(first_name="Павло", last_name="Вільнюк")
        self.mine = Contact.objects.create(first_name="Ганна", last_name="Моя", owner=self.mgr)
        self.conv_ivana = Conversation.objects.create(channel=self.ch, contact=self.ivana, external_chat_id="comment:1",
                                                      title="facebook · коментар", assigned_to=self.laptev)
        self.conv_pavlo = Conversation.objects.create(channel=self.ch, contact=self.pavlo, external_chat_id="2", title="")
        self.deal = Deal.objects.create(title="Декор", contact=self.ivana, funnel=self.funnel, stage=self.stage,
                                        amount=Decimal("100"), owner=self.laptev)

    def search(self, user, q):
        c = APIClient()
        c.force_authenticate(user)
        r = c.get("/api/search/", {"q": q})
        self.assertEqual(r.status_code, 200)
        return r.json()

    @staticmethod
    def ids(res, key):
        return [x["id"] for x in res[key]]

    def test_full_name_any_order_case_latin(self):
        for q in ("Івана Забурко", "Забурко Івана", "  Івана   Забурко ", "забурко", "ЗАБУР", "Ivana", "Zaburko",
                  "ivana zaburko"):
            r = self.search(self.owner, q)
            self.assertIn(self.ivana.id, self.ids(r, "clients"), q)
            self.assertIn(self.conv_ivana.id, self.ids(r, "chats"), q)
            self.assertIn(self.deal.id, self.ids(r, "deals"), q)

    def test_multi_word_every_word_must_match(self):
        r = self.search(self.owner, "Івана Коваль")
        self.assertNotIn(self.ivana.id, self.ids(r, "clients"))
        self.assertNotIn(self.maryana.id, self.ids(r, "clients"))

    def test_nickname_and_link(self):
        for q in ("@daria_atanova66", "daria_atanova", "https://instagram.com/daria_atanova66?igsh=x"):
            self.assertIn(self.daria.id, self.ids(self.search(self.owner, q), "clients"), q)

    def test_phone_any_format(self):
        for q in ("0638682204", "+380638682204", "063 868 22 04", "+38 (063) 868-22-04", "868-22-04"):
            self.assertIn(self.maryana.id, self.ids(self.search(self.owner, q), "clients"), q)

    def test_apostrophe_variants(self):
        for q in ("Мар'яна", "Мар’яна", "Марʼяна Коваль", "коваль мар'яна"):
            self.assertIn(self.maryana.id, self.ids(self.search(self.owner, q), "clients"), q)

    def test_deal_by_number(self):
        r = self.search(self.owner, "#%d" % self.deal.id)
        self.assertIn(self.deal.id, self.ids(r, "deals"))

    def test_manager_scope_respected(self):
        r = self.search(self.mgr, "Забурко")
        self.assertEqual(self.ids(r, "clients"), [])       # чужий клієнт (власник — Лаптев)
        self.assertEqual(self.ids(r, "chats"), [])         # чат закріплений за іншим
        self.assertEqual(self.ids(r, "deals"), [])
        r = self.search(self.mgr, "Павло Вільнюк")
        self.assertIn(self.conv_pavlo.id, self.ids(r, "chats"))   # вільний пул — видно, як у «Чатах»
        self.assertEqual(self.ids(r, "clients"), [])
        r = self.search(self.mgr, "Ганна Моя")
        self.assertIn(self.mine.id, self.ids(r, "clients"))

    def test_chats_need_inbox_permission(self):
        r = self.search(self.no_inbox, "Павло")
        self.assertEqual(r["chats"], [])

    def test_short_query(self):
        r = self.search(self.owner, "a")
        self.assertEqual(r, {"deals": [], "leads": [], "clients": [], "chats": []})
