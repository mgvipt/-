"""19.09.2026 (сделка #66787): повернення товару з товарного кредиту закриває борг і зайву задачу складу."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.crm.models import Task
from apps.finance.models import PlannedPayment
from apps.warehouse.models import WarehouseJob

from . import services
from .tests import _Base


class CreditReturnTests(_Base):
    def _credit(self, d, amount, paid=0):
        return PlannedPayment.objects.create(kind="receivable", amount=Decimal(str(amount)), paid_amount=Decimal(str(paid)),
                                             due_date=timezone.localdate() + timedelta(days=14), deal=d,
                                             counterparty="Салон", comment="Товарний кредит зі сделки #%s (14 дн.)" % d.id)

    def _job(self, d):
        t = Task.objects.create(title="Відвантажити #%s" % d.id, kind="warehouse", deal=d)
        return WarehouseJob.objects.create(deal=d, task=t)

    def test_full_return_cancels_debt_and_queued_job(self):
        d, it = self.deal(qty=1, price=155, cost=110, realize=False)
        pp = self._credit(d, 155)
        job = self._job(d)
        services.register_return(d, self.mgr, {"reason": "changed_mind", "lines": [{"item": it.id, "quantity": 1}]})
        pp.refresh_from_db(); job.refresh_from_db()
        self.assertEqual(pp.status, "canceled")
        self.assertEqual(pp.amount, Decimal("0.00"))
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(job.task.status, "canceled")

    def test_partial_return_reduces_debt_and_keeps_job(self):
        d, it = self.deal(qty=2, price=100, cost=50, realize=False)
        pp = self._credit(d, 200)
        job = self._job(d)
        services.register_return(d, self.mgr, {"reason": "changed_mind", "lines": [{"item": it.id, "quantity": 1}]})
        pp.refresh_from_db(); job.refresh_from_db()
        self.assertEqual(pp.amount, Decimal("100.00"))
        self.assertEqual(pp.status, "planned")
        self.assertEqual(job.status, "queued")          # ще є що відвантажити

    def test_partly_paid_debt_closes_as_paid(self):
        d, it = self.deal(qty=1, price=155, cost=110, realize=False)
        pp = self._credit(d, 155, paid=55)
        services.register_return(d, self.mgr, {"reason": "changed_mind", "lines": [{"item": it.id, "quantity": 1}]})
        pp.refresh_from_db()
        self.assertEqual(pp.amount, Decimal("55.00"))   # погашену частину не чіпаємо
        self.assertEqual(pp.status, "paid")
