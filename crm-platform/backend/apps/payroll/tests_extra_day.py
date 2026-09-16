"""16.09.2026 (Олег): лишній день понад норму — подвійна ставка дня, не більше 1 на місяць."""
from datetime import date, timedelta

from apps.finance.models import WorkDay

from . import engine
from . import tests as _t
from .models import PayComponent


class ExtraDayTests(_t.PayrollEngineTests):
    for _n in [n for n in dir(_t.PayrollEngineTests) if n.startswith("test_")]:
        locals()[_n] = None
    del _n

    def _worked(self, n):
        d = date(2026, 9, 1)
        for i in range(n):
            WorkDay.objects.create(user=self.mgr, date=d + timedelta(days=i), status="worked")

    def test_one_extra_day_paid_double(self):
        s = self._scheme(valid_from=date(2026, 9, 1))
        PayComponent.objects.create(scheme=s, kind="base_by_days", params={"amount": 22000})
        self._worked(23)                       # норма вересня 22 → 1 лишній день
        self.assertEqual(engine.calc(self.mgr, "2026-09")["total"], 22000 + 2000)

    def test_only_one_extra_day_per_month(self):
        s = self._scheme(valid_from=date(2026, 9, 1))
        PayComponent.objects.create(scheme=s, kind="base_by_days", params={"amount": 22000})
        self._worked(25)
        r = engine.calc(self.mgr, "2026-09")
        self.assertEqual(r["total"], 24000)
        self.assertIn("лише 1 на місяць", r["lines"][0]["detail"])
