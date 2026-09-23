# -*- coding: utf-8 -*-
"""23.09.2026 (Олег): клієнт забирає в салоні — посилка не їде, склад не пакує,
після «Готово» задача і сделка закриваються."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.warehouse import weight_rules as WR
from apps.warehouse.models import WarehouseJob
from apps.warehouse.wh_views import _close_pickup_deal, _is_pickup, _required_photo_kinds


class PickupSalonTests(TestCase):
    def setUp(self):
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.s0 = Stage.objects.create(funnel=self.f, name="Відвантаження", order=5)
        self.won = Stage.objects.create(funnel=self.f, name="Успішна угода", order=14, is_won=True)
        self.c = Contact.objects.create(first_name="Клієнт салону")
        self.u = get_user_model().objects.create(username="sklad")

    def _deal(self, pickup):
        return Deal.objects.create(title="Замовлення", funnel=self.f, stage=self.s0, contact=self.c,
                                   amount=Decimal("1000"), qualification={"pickup_salon": True} if pickup else {})

    def test_pickup_is_like_salon_no_packing(self):
        self.assertTrue(WR.is_salon(self._deal(True)))
        self.assertFalse(WR.is_salon(self._deal(False)))

    def test_no_parcel_photo_for_pickup(self):
        job = WarehouseJob.objects.create(deal=self._deal(True))
        self.assertEqual(_required_photo_kinds(job), ["buckets", "invoice"])
        job2 = WarehouseJob.objects.create(deal=self._deal(False))
        self.assertEqual(_required_photo_kinds(job2), ["buckets", "parcel", "invoice"])

    def test_is_pickup_reads_deal_and_job(self):
        job = WarehouseJob.objects.create(deal=self._deal(True))
        self.assertTrue(_is_pickup(job))
        self.assertTrue(_is_pickup(job.deal))
        self.assertFalse(_is_pickup(self._deal(False)))

    def test_deal_closes_after_pickup(self):
        d = self._deal(True)
        _close_pickup_deal(d, self.u)
        d.refresh_from_db()
        self.assertTrue(d.stage.is_won)

    def test_closed_deal_not_touched(self):
        d = self._deal(True)
        d.stage = self.won
        d.save()
        _close_pickup_deal(d, self.u)
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.won.id)
