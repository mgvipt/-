"""19.09.2026: прихід без сделки, схожий на оплату клієнта (кейс #66537) → сповіщення, один раз."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.inbox.models import Notification

from .models import Account, Transaction
from .unlinked import find, notify


class UnlinkedIncomeTests(TestCase):
    def setUp(self):
        self.mgr = User.objects.create_user(username="kirill_t", password="x")
        f = Funnel.objects.create(name="21 Основний продукт")
        Stage.objects.create(funnel=f, name="Розрахунок здійснено (КП)", order=1)
        ign = Stage.objects.create(funnel=f, name="Игнор", order=19, is_lost=True)
        c = Contact.objects.create(first_name="Крістіна", last_name="Круглова", phone="+380983434822")
        self.deal = Deal.objects.create(title="Галатея", funnel=f, stage=ign, contact=c, amount=Decimal("2261.50"),
                                        owner=self.mgr)
        self.acc = Account.objects.create(name="Поступ | ФОП ОНЛ (1493)")

    def _tx(self, comment, amount="2261.50"):
        return Transaction.objects.create(direction="in", amount=Decimal(amount), amount_uah=Decimal(amount),
                                          account=self.acc, date=date.today(), comment=comment)

    def test_order_number_in_lost_deal_is_found_and_notified_once(self):
        tx = self._tx("PB#X · Оплата згідно замовлення #%s, Круглова Крістіна" % self.deal.id)
        rows = find()
        self.assertEqual([(r["tx"].id, r["deal"].id) for r in rows], [(tx.id, self.deal.id)])
        self.assertEqual(notify(rows), 1)
        self.assertTrue(Notification.objects.filter(user=self.mgr, text__contains="журнал #%s" % tx.id).exists())
        self.assertEqual(notify(find()), 0)          # вдруге не шлемо

    def test_surname_and_amount_without_number(self):
        self._tx("PB#Y · Переказ від Круглова К.О.")
        self.assertEqual(find()[0]["why"], "прізвище клієнта + сума")

    def test_foreign_income_is_quiet(self):
        self._tx("Погашення відсотків за користування лімітом", amount="1388.63")
        self.assertEqual(find(), [])
