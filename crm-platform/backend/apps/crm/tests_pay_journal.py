"""19.09.2026 (Олег): «Прийняти оплату → З журналу» — привʼязати прихід, що вже є в журналі; лише за явним правом."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.finance.models import Account, Transaction

from .models import Contact, Deal, Funnel, Stage


class PayFromJournalTests(TestCase):
    def setUp(self):
        f = Funnel.objects.create(name="21 Основний продукт")
        Stage.objects.create(funnel=f, name="Розрахунок здійснено (КП)", order=1)
        Stage.objects.create(funnel=f, name="Домовились про оплату", order=2)
        self.paid_stage = Stage.objects.create(funnel=f, name="Оплату отримано", order=3)
        c = Contact.objects.create(first_name="Крістіна", last_name="Круглова")
        self.boss = User.objects.create_superuser(username="boss_j", password="x")
        self.deal = Deal.objects.create(title="Галатея", funnel=f, stage=f.stages.first(), contact=c,
                                        amount=Decimal("2261.50"), owner=self.boss)
        acc = Account.objects.create(name="ФОП ОНЛ")
        self.tx = Transaction.objects.create(direction="in", amount=Decimal("2261.50"), amount_uah=Decimal("2261.50"),
                                             account=acc, date=date.today(),
                                             comment="Оплата згідно замовлення #%s, Круглова" % self.deal.id)
        self.other = Transaction.objects.create(direction="in", amount=Decimal("100"), amount_uah=Decimal("100"),
                                                account=acc, date=date.today(), comment="інше")

    def _staff(self, username, extra=()):
        role = Role.objects.create(name="Менеджер " + username, permissions=["deal.view", "deal.view.all", "deal.edit.all", "payment.process"])
        return User.objects.create_user(username=username, password="x", role=role, account_kind="staff",
                                        extra_permissions=list(extra))

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_owner_sees_matching_income_first_and_links_it(self):
        c = self._client(self.boss)
        r = c.get("/api/deals/%s/journal_candidates/" % self.deal.id)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["rows"][0]["id"], self.tx.id)
        self.assertTrue(r.data["rows"][0]["suggested"])
        r = c.post("/api/deals/%s/link_journal/" % self.deal.id, {"tx_id": self.tx.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.tx.refresh_from_db(); self.deal.refresh_from_db()
        self.assertEqual(self.tx.deal_id, self.deal.id)
        self.assertEqual(self.deal.stage_id, self.paid_stage.id)
        self.assertEqual([float(p.amount) for p in self.deal.payments.filter(is_paid=True)], [2261.5])
        again = c.post("/api/deals/%s/link_journal/" % self.deal.id, {"tx_id": self.tx.id}, format="json")
        self.assertEqual(again.status_code, 409)                 # вдруге не двоїмо

    def test_manager_without_right_is_refused_even_if_methods_unlimited(self):
        m = self._staff("mgr_j")
        self.assertEqual(self._client(m).get("/api/deals/%s/journal_candidates/" % self.deal.id).status_code, 403)

    def test_manager_with_explicit_right_can_link(self):
        m = self._staff("ilona_j", ["payment.method.journal"])
        Deal.objects.filter(id=self.deal.id).update(owner=m)
        r = self._client(m).post("/api/deals/%s/link_journal/" % self.deal.id, {"tx_id": self.tx.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
