"""Пошук у «Чатах» (/api/conversations/?search=…) — 15.09.2026, chatsearch.

Було: «Івана Забурко» (імʼя + прізвище разом), «@нік», інший апостроф, латиниця — 0 результатів;
закриті чати пошук не знаходив; права доступу при пошуку мають лишитись як були.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.inbox.models import Channel, Conversation


class ChatSearchTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("chs2-owner", password="x")
        self.laptev = User.objects.create_user("chs2-laptev", password="x")
        role = Role.objects.create(name="Менеджер (чати тест)", permissions=["inbox.view"])
        self.mgr = User.objects.create_user("chs2-mgr", password="x", role=role)
        ch = Channel.objects.create(kind="telegram", name="TG тест")
        mk = Contact.objects.create
        self.ivana = mk(first_name="Івана", last_name="Забурко")
        self.maryana = mk(first_name="Марʼяна", last_name="Коваль", phone="+38 (063) 868-22-04")
        self.daria = mk(first_name="Stepanova", last_name="Daria", nickname="daria_atanova66",
                        social_link="https://instagram.com/daria_atanova66")
        self.olena = mk(first_name="Олена", last_name="Стридинская")
        self.pavlo = mk(first_name="Павло", last_name="Вільнюк")
        cv = Conversation.objects.create
        self.c_ivana = cv(channel=ch, contact=self.ivana, external_chat_id="comment:1", title="facebook · коментар",
                          assigned_to=self.laptev)
        self.c_maryana = cv(channel=ch, contact=self.maryana, external_chat_id="2", assigned_to=self.owner)
        self.c_daria = cv(channel=ch, contact=self.daria, external_chat_id="3", assigned_to=self.owner)
        self.c_closed = cv(channel=ch, contact=self.olena, external_chat_id="4", status="closed", assigned_to=self.owner)
        self.c_site = cv(channel=ch, contact=None, external_chat_id="5", title="[site] Гість сайту Оксана")
        self.c_pavlo = cv(channel=ch, contact=self.pavlo, external_chat_id="6")

    def ids(self, user, **params):
        c = APIClient()
        c.force_authenticate(user)
        r = c.get("/api/conversations/", dict({"page_size": "50"}, **params))
        self.assertEqual(r.status_code, 200)
        return [x["id"] for x in r.json()["results"]]

    def test_full_name_any_order_and_case(self):
        for q in ("Івана Забурко", "Забурко Івана", "  Івана   Забурко ", "забурко", "ЗАБУРКО", "Забур", "Івана"):
            self.assertIn(self.c_ivana.id, self.ids(self.owner, search=q), q)

    def test_latin_to_cyrillic(self):
        for q in ("Ivana", "Zaburko", "ivana zaburko"):
            self.assertIn(self.c_ivana.id, self.ids(self.owner, search=q), q)

    def test_nickname_with_at_and_link(self):
        for q in ("@daria_atanova66", "daria_atanova", "https://instagram.com/daria_atanova66/"):
            self.assertIn(self.c_daria.id, self.ids(self.owner, search=q), q)

    def test_phone_any_format(self):
        for q in ("0638682204", "+380638682204", "063 868 22 04", "+38 (063) 868-22-04"):
            self.assertIn(self.c_maryana.id, self.ids(self.owner, search=q), q)

    def test_apostrophe_variants(self):
        for q in ("Мар'яна Коваль", "Мар’яна", "Марʼяна"):
            self.assertIn(self.c_maryana.id, self.ids(self.owner, search=q), q)

    def test_closed_chats_only_when_searching(self):
        self.assertNotIn(self.c_closed.id, self.ids(self.owner))
        self.assertIn(self.c_closed.id, self.ids(self.owner, search="Стридинская"))

    def test_chat_without_contact_by_title(self):
        self.assertIn(self.c_site.id, self.ids(self.owner, search="Оксана"))

    def test_chat_and_deal_numbers(self):
        self.assertIn(self.c_ivana.id, self.ids(self.owner, search="#%d" % self.c_ivana.id))
        f = Funnel.objects.create(name="Основна (тест)")
        s = Stage.objects.create(funnel=f, name="Новий", order=0)
        d = Deal.objects.create(title="Декор", contact=self.ivana, funnel=f, stage=s)
        self.assertIn(self.c_ivana.id, self.ids(self.owner, search=str(d.id)))

    def test_every_word_must_match(self):
        self.assertEqual(self.ids(self.owner, search="Івана Коваль"), [])

    def test_access_scope_kept_when_searching(self):
        # менеджер без «всі чати»: чужий закріплений чат не знаходить навіть пошуком (вкладка «Мої»)
        self.assertNotIn(self.c_ivana.id, self.ids(self.mgr, scope="mine", search="Забурко"))
        # вільний (нічий) чат — спільний пул: знаходить, вкладка «Мої» пошук не обмежує
        self.assertIn(self.c_pavlo.id, self.ids(self.mgr, scope="mine", search="Вільнюк Павло"))
        # відповідальний знаходить свій
        self.assertIn(self.c_ivana.id, self.ids(self.laptev, scope="mine", search="Івана Забурко"))
