"""16.09.2026 (Олег): гарантія новачку з 2-го місяця залежить від плану (повністю / пропорційно / не менше 50%)."""
from datetime import date
from decimal import Decimal

from apps.crm.models import Contact, Deal
from apps.finance.models import ManagerPlan, Transaction

from . import engine
from .models import PayComponent
from . import tests as _t


class NewcomerPlanGuaranteeTests(_t.PayrollEngineTests):
    # успадковуємо setUp/_scheme; тести базового класу тут не дублюємо
    for _n in [n for n in dir(_t.PayrollEngineTests) if n.startswith("test_")]:
        locals()[_n] = None
    del _n
    def _setup(self, sold):
        s = self._scheme(valid_from=date(2026, 9, 1))
        g = PayComponent.objects.create(scheme=s, kind="guarantee",
                                        params={"amount": 15000, "months": 2, "start": "2026-09-01",
                                                "checks": {"2026-09": {"ok": True}, "2026-10": {"ok": True}}})
        ManagerPlan.objects.create(user=self.mgr, period="2026-10", target_revenue=Decimal("50000"))
        if sold:
            d = Deal.objects.create(title="d", funnel=self.funnel, stage=self.st, contact=Contact.objects.create(first_name="К"),
                                    amount=sold, owner=self.mgr)
            Transaction.objects.create(direction="in", amount=Decimal(sold), amount_uah=Decimal(sold), date=date(2026, 10, 5), deal=d, account=self.acc)
        return g

    def test_first_month_full_guarantee(self):
        self._setup(0)
        self.assertEqual(engine.calc(self.mgr, "2026-09")["total"], 15000)

    def test_second_month_plan_met_full(self):
        self._setup(50000)
        line = [l for l in engine.calc(self.mgr, "2026-10")["lines"] if l.get("kind") == "guarantee"][0]
        self.assertEqual(line["basis"], 15000)

    def test_second_month_plan_half_scaled_with_floor(self):
        self._setup(35000)   # 70% плану → гарантія 70% = 10 500
        line = [l for l in engine.calc(self.mgr, "2026-10")["lines"] if l.get("kind") == "guarantee"][0]
        self.assertEqual(line["basis"], 10500)
        self.assertIn("гарантія 70%", line["detail"])

    def test_second_month_low_sales_floor_50(self):
        self._setup(5000)    # 10% плану → не менше 50% = 7 500
        line = [l for l in engine.calc(self.mgr, "2026-10")["lines"] if l.get("kind") == "guarantee"][0]
        self.assertEqual(line["basis"], 7500)
