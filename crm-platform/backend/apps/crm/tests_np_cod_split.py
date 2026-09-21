# -*- coding: utf-8 -*-
"""Наложка на посилці з дозамовленням (21.09.2026, Олег: розбір #66531 + #66546).

Одна ТТН — кілька сделок: платіж має створитись по КОЖНІЙ, на суму її боргу,
з номером «ТТН#номер сделки». Сделку, оплачену іншим способом, наложка не чіпає.
"""
from decimal import Decimal

from django.test import TestCase

from apps.crm.management.commands.np_status_sync import _record_cod_payment
from apps.crm.models import Deal, Funnel, Payment, Stage

TTN = "20451528063103"


class CodSplitTests(TestCase):
    def setUp(self):
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Отримано", order=10)

    def _deal(self, amount, cod, parent=None):
        return Deal.objects.create(title="t", funnel=self.f, stage=self.st, amount=Decimal(amount),
                                   ttn=TTN, parent_deal=parent, np_data={"cod_amount": cod})

    def test_parent_and_child_both_get_payment(self):
        parent = self._deal("1439.00", 939)
        Payment.objects.create(deal=parent, provider="reqs", amount=Decimal("500"), is_paid=True)
        child = self._deal("91.80", 92, parent=parent)

        _record_cod_payment(child, cod_hint=1031)      # дозамовлення обробилось першим — як у житті
        _record_cod_payment(parent, cod_hint=1031)

        pc = Payment.objects.get(deal=child, provider="np_cod")
        pp = Payment.objects.get(deal=parent, provider="np_cod")
        self.assertEqual(pc.amount, Decimal("91.80"))          # борг сделки, а не округлені 92
        self.assertEqual(pp.amount, Decimal("939.00"))         # 1439 − 500 передоплати
        self.assertEqual(pc.external_id, "%s#%s" % (TTN, child.id))
        self.assertEqual(pp.external_id, "%s#%s" % (TTN, parent.id))
        self.assertEqual(pc.amount + pp.amount, Decimal("1030.80"))   # = наложка посилки

    def test_paid_deal_gets_no_cod(self):
        d = self._deal("420.30", 420)
        Payment.objects.create(deal=d, provider="reqs", amount=Decimal("420.30"), is_paid=True)
        _record_cod_payment(d, cod_hint=420)
        self.assertFalse(Payment.objects.filter(deal=d, provider="np_cod").exists())

    def test_idempotent(self):
        d = self._deal("300.00", 300)
        _record_cod_payment(d)
        _record_cod_payment(d)
        self.assertEqual(Payment.objects.filter(deal=d, provider="np_cod").count(), 1)
