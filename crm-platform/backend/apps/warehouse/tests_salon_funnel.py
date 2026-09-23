# -*- coding: utf-8 -*-
"""23.09.2026 (інцидент #66361 Стельмах): салонна угода «4.С/Алмазне + Вентиляція» потрапила в онлайн —
CRM вимагала ТТН і склад не міг закрити задачу."""
from django.test import TestCase

from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.warehouse import weight_rules as WR
from apps.warehouse.models import WarehouseJob
from apps.warehouse.wh_views import _job_dict, _required_photo_kinds


class SalonFunnelTests(TestCase):
    def _deal(self, funnel_name, ttn="", qual=None):
        f = Funnel.objects.create(name=funnel_name)
        st = Stage.objects.create(funnel=f, name="Відвантаження", order=5)
        c = Contact.objects.create(first_name="Клієнт")
        return Deal.objects.create(title="Угода", funnel=f, stage=st, contact=c, ttn=ttn, qualification=qual or {})

    def test_salon_funnels_are_offline(self):
        for name in ("4.С/Алмазне + Вентиляція", "1.С/Покрытия для стен", "6.С/ОПТ_Дилеры"):
            job = WarehouseJob.objects.create(deal=self._deal(name))
            self.assertEqual(_job_dict(job)["channel"], "offline", name)

    def test_online_funnels_stay_online(self):
        for name in ("21 Основний продукт", "22 Тестовий набір", "23 Інтернет-магазин wallcov.com.ua"):
            job = WarehouseJob.objects.create(deal=self._deal(name))
            self.assertEqual(_job_dict(job)["channel"], "online", name)

    def test_salon_without_ttn_has_no_parcel_photo(self):
        job = WarehouseJob.objects.create(deal=self._deal("4.С/Алмазне + Вентиляція"))
        self.assertEqual(_required_photo_kinds(job), ["buckets", "invoice"])

    def test_salon_with_ttn_is_a_parcel(self):
        job = WarehouseJob.objects.create(deal=self._deal("1.С/Покрытия для стен", ttn="20450000000000"))
        self.assertIn("parcel", _required_photo_kinds(job))
        self.assertFalse(WR.is_salon(job.deal))

    def test_pickup_flag_still_offline(self):
        job = WarehouseJob.objects.create(deal=self._deal("21 Основний продукт", qual={"pickup_salon": True}))
        self.assertEqual(_job_dict(job)["channel"], "offline")
