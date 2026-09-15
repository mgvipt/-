"""15.09.2026: бюджет найму — ціни з задач біржі; кожна відкрита вакансія додає свій бюджет у ліміт «Біржі задач»."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.bounty import services as S
from apps.bounty.models import TaskCategory, TaskOffer
from apps.finance.models import FinModelArticle
from apps.payroll.models import PayScheme


class HiringBudgetTests(TestCase):
    def setUp(self):
        c1 = TaskCategory.objects.create(department="hr", name="Вакансії і пошук")
        c2 = TaskCategory.objects.create(department="hr", name="Адаптація і навчання")
        for cat, title, price in ((c1, "Знайшов співробітника: продажі або салон", 500), (c1, "Знайшов співробітника: склад або офіс", 300),
                                  (c1, "Рекомендований вами новачок відпрацював місяць: продажі або салон", 500),
                                  (c2, "Навчив новачка — відпрацював перший місяць: продажі або салон", 2000),
                                  (c2, "Навчив новачка — відпрацював перший місяць: склад або офіс", 1200)):
            TaskOffer.objects.create(category=cat, title=title, price=Decimal(price), active=True)
        TaskOffer.objects.create(category=c1, title="Вимкнена: продажі або салон", price=Decimal("9999"), active=False)

    def test_budget_by_group(self):
        b = S.hiring_budget()
        self.assertEqual((b["sales"], b["ops"]), (Decimal("3000"), Decimal("1500")))
        self.assertEqual((S.hiring_group("Продажі"), S.hiring_group("Склад"), S.hiring_group("Маркетинг")), ("sales", "ops", "ops"))

    def test_open_vacancy_adds_budget_to_fund_limit(self):
        FinModelArticle.objects.create(category="variable", name="Біржа задач", value=Decimal("0"), value_type="fixed_sum_per_month")
        self.assertFalse(S.fund_info()["enforced"])
        PayScheme.objects.create(position="Менеджер салону", department="Продажі", valid_from=date(2026, 11, 1),
                                 is_vacancy=True, planned_start=date(2026, 11, 1))
        f = S.fund_info()
        self.assertTrue(f["enforced"])
        self.assertEqual(f["limit"], 3000.0)
        self.assertEqual([v["amount"] for v in f["vacancies"]], [3000.0])
