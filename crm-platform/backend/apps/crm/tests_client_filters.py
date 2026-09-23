from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.crm.models import Contact, Deal, DealItem, Funnel, Payment, Stage
from apps.warehouse.models import Product


class ClientPurchaseFiltersTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="client-filter-admin",
            email="filters@example.com",
            password="x",
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)

        self.funnel = Funnel.objects.create(name="Продажі")
        self.open_stage = Stage.objects.create(funnel=self.funnel, name="Нова", order=0)
        self.won_stage = Stage.objects.create(
            funnel=self.funnel, name="Успішна", order=10, is_won=True
        )

        self.micro = Product.objects.create(name="Microcement Wallcov", sku="MICRO")
        self.fine = Product.objects.create(name="Pattera Fine", sku="FINE")
        self.draft_product = Product.objects.create(name="Чернетка товару", sku="DRAFT")

        self.phone = Contact.objects.create(
            first_name="Телефон", phone="+380501111111",
            source="instagram", loyalty_tag="VIP",
        )
        self.email = Contact.objects.create(
            first_name="Email", email="email@example.com",
            source="site", loyalty_tag="Активний",
        )
        self.both = Contact.objects.create(
            first_name="Обидва", phone="+380502222222", email="both@example.com",
            source="call", loyalty_tag="Новий",
        )
        self.empty = Contact.objects.create(first_name="Без контактів", source="manual-source")

        paid_deal = Deal.objects.create(
            title="Оплачений мікроцемент", contact=self.phone,
            funnel=self.funnel, stage=self.open_stage,
        )
        DealItem.objects.create(deal=paid_deal, product=self.micro, quantity=1, price=100)
        Payment.objects.create(
            deal=paid_deal, provider="cash", amount=100, is_paid=True,
        )

        won_deal = Deal.objects.create(
            title="Закритий Pattera", contact=self.email,
            funnel=self.funnel, stage=self.won_stage,
        )
        DealItem.objects.create(deal=won_deal, product=self.fine, quantity=1, price=200)

        draft_deal = Deal.objects.create(
            title="Не купив", contact=self.both,
            funnel=self.funnel, stage=self.open_stage,
        )
        DealItem.objects.create(
            deal=draft_deal, product=self.draft_product, quantity=1, price=300,
        )

        # Захист від змішування різних угод одного контакту:
        # оплачена угода без товару не повинна перетворити чернетку на покупку.
        other_paid = Deal.objects.create(
            title="Інша оплачена", contact=self.both,
            funnel=self.funnel, stage=self.open_stage,
        )
        Payment.objects.create(
            deal=other_paid, provider="cash", amount=50, is_paid=True,
        )

    def names(self, response):
        self.assertEqual(response.status_code, 200)
        return {row["display_name"] for row in response.json()["results"]}

    def test_list_shows_only_paid_or_won_materials(self):
        response = self.api.get("/api/contacts/", {"page_size": 20})
        self.assertEqual(response.status_code, 200)
        rows = {row["display_name"]: row for row in response.json()["results"]}
        self.assertEqual(
            rows["Телефон"]["purchased_materials"],
            [{"id": self.micro.id, "name": "Microcement Wallcov"}],
        )
        self.assertEqual(
            rows["Email"]["purchased_materials"],
            [{"id": self.fine.id, "name": "Pattera Fine"}],
        )
        self.assertEqual(rows["Обидва"]["purchased_materials"], [])

    def test_contact_methods_are_a_multiselect_with_or_semantics(self):
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"contact_in": "phone"})),
            {"Телефон", "Обидва"},
        )
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"contact_in": "email"})),
            {"Email", "Обидва"},
        )
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"contact_in": "phone,email"})),
            {"Телефон", "Email", "Обидва"},
        )

    def test_sources_statuses_and_materials_accept_multiple_values(self):
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"source_in": "instagram,site"})),
            {"Телефон", "Email"},
        )
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"loyalty_in": "VIP,Новий"})),
            {"Телефон", "Обидва"},
        )
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"material_ids": str(self.micro.id)})),
            {"Телефон"},
        )
        self.assertEqual(
            self.names(self.api.get("/api/contacts/", {"material_ids": str(self.draft_product.id)})),
            set(),
        )

    def test_filter_options_use_visible_real_values_and_purchases(self):
        response = self.api.get("/api/contacts/filter-options/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(
            {"instagram", "site", "call", "manual-source"}.issubset(
                {row["value"] for row in payload["sources"]}
            )
        )
        self.assertTrue({"VIP", "Активний", "Новий"}.issubset(set(payload["statuses"])))
        self.assertEqual(
            {row["name"] for row in payload["materials"]},
            {"Microcement Wallcov", "Pattera Fine"},
        )
