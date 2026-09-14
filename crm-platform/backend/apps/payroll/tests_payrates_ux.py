"""Ставки співробітників — підказки «звідки ця сума» (14.09.2026, payrates-ux).

Перевіряємо: розшифровка податків (трудовий / ФОП / без оформлення) сходиться з підсумком;
пояснення твердої частини (оклад + стандарт, гарантія до дати); СТАРІ числа scheme_cost не змінились
(порівняння з копією функції до патчу); ставки складу — ті самі статті Фінмоделі (одне джерело)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from apps.finance.models import FinModelArticle
from apps.payroll import engine
from apps.payroll.models import PayComponent, PayPolicy, PayScheme

HOST = "crm.wallcovdec.com.ua"
ON = date(2026, 9, 20)
OLD_KEYS = ("fixed_net", "fixed_cost", "margin_pct", "revenue_pct", "piece_pct", "taxes_ratio", "guarantee", "parts")


def _old_scheme_cost(sc, pol=None, sh=None, on=None):
    """Дослівна копія engine.scheme_cost ДО патчу (HEAD f28132f2) — еталон «числа не змінились»."""
    from django.utils import timezone
    pol = pol or engine.policy()
    sh = sh or engine.shares(pol)
    on = on or timezone.localdate()
    fixed_net, m_pct, r_pct, parts = 0.0, 0.0, 0.0, []
    piece_pct = 0.0
    guarantee = 0.0
    for c in sc.components.filter(active=True):
        p = c.params or {}
        if c.kind in ("base_by_days", "fixed_monthly"):
            fixed_net += float(p.get("amount") or 0)
            parts.append((c.title or c.get_kind_display(), float(p.get("amount") or 0), "₴"))
        elif c.kind == "standard":
            fixed_net += float(p.get("max") or 0)
            parts.append((c.title or "Стандарт (максимум)", float(p.get("max") or 0), "₴"))
        elif c.kind == "guarantee":
            g_start, g_end = engine.guarantee_window(c)
            ref = sc.planned_start if sc.is_vacancy and sc.planned_start else on
            if sc.is_vacancy or (g_start and g_start <= ref <= g_end):
                guarantee = float(p.get("amount") or pol["guarantee"]["amount"])
        elif c.kind == "margin_share":
            funnels = p.get("funnels") or pol["funnels"]["online"]
            own = sum(sh["by_owner_margin"].get((sc.user_id, f), 0) for f in funnels) if sc.user_id else 0.0
            share = (own / sh["margin_total"]) if (sh["margin_total"] and not sc.is_vacancy) else 0.0
            add = float(p.get("pct_to_plan", 10)) / 100 * share
            m_pct += add
            parts.append((c.title or "% з маржі", round(add * 100, 2), "% маржі"))
        elif c.kind == "revenue_share":
            pct = float(p.get("pct") or 0) / 100
            if p.get("basis") in ("object_acts", "objects_income"):
                share = sh["objects_rev"] / sh["rev_total"] if sh["rev_total"] else 0
            elif p.get("basis") == "own_payments":
                own = sum(v for (o, _f), v in sh["by_owner_rev"].items() if o == sc.user_id) if sc.user_id else 0.0
                share = own / sh["rev_total"] if sh["rev_total"] else 0
            elif p.get("own_only", True) and sc.user_id:
                own = sum(sh["by_owner_rev"].get((sc.user_id, f), 0) for f in (p.get("funnels") or []))
                share = own / sh["rev_total"] if sh["rev_total"] else 0
            else:
                share = (sum(sh["by_funnel_rev"].get(f, 0) for f in (p.get("funnels") or [])) / sh["rev_total"]) if sh["rev_total"] else 0
            add = pct * share
            r_pct += add
            parts.append((c.title or "% з обороту", round(add * 100, 2), "% виручки"))
        elif c.kind == "piece_rate" and sc.user_id and sh["rev_total"]:
            from apps.warehouse.models import WarehousePayrollEntry
            s = float(WarehousePayrollEntry.objects.filter(employee_id=sc.user_id, work_date__gte=sh["from"],
                                                           work_date__lte=sh["to"], status="confirmed")
                      .aggregate(x=Sum("amount"))["x"] or 0)
            add = s / sh["rev_total"]
            r_pct += add
            piece_pct += add
            parts.append((c.title or "Відрядно", round(add * 100, 2), "% виручки"))
    fixed_net = max(fixed_net, guarantee)
    ratio = engine._pct_ratio(sc.employment, pol)
    return {"fixed_net": round(fixed_net), "fixed_cost": round(engine.employer_cost(fixed_net, sc.employment, pol)),
            "margin_pct": m_pct * ratio, "revenue_pct": r_pct * ratio, "piece_pct": piece_pct * ratio, "taxes_ratio": round(ratio, 3),
            "guarantee": guarantee, "parts": parts}


class PayCostExplainTests(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.owner = U.objects.create_superuser("prux-owner", "prux-o@example.test", "x")
        self.mgr = U.objects.create_user("prux-mgr", "prux-m@example.test", "x", first_name="Тест", last_name="Новачок")
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        self.pol = engine.policy()
        self.sh = engine.shares(self.pol, today=ON)

    def _newbie(self, employment, user=None):
        """Як у Лаптева: оклад за вихід 6 000 + стандарт до 6 000 + % з маржі + гарантія 15 000 з 14.09 на 2 міс."""
        s = PayScheme.objects.create(user=user or self.mgr, position="Менеджер (новачок)", department="Продажі",
                                     valid_from=date(2026, 9, 14), employment=employment)
        PayComponent.objects.create(scheme=s, kind="base_by_days", title="За вихід (по табелю)", params={"amount": 6000}, order=0)
        PayComponent.objects.create(scheme=s, kind="standard", title="Стандарт роботи (до 6 000 ₴)", params={"max": 6000}, order=1)
        PayComponent.objects.create(scheme=s, kind="margin_share", params={"funnels": [15, 16], "pct_to_plan": 10, "pct_over_plan": 20}, order=2)
        PayComponent.objects.create(scheme=s, kind="guarantee", params={"amount": 15000, "months": 2, "start": "2026-09-14"}, order=3)
        return s

    def _cost(self, s, on=ON, pol=None):
        return engine.scheme_cost(s, pol or self.pol, self.sh, on)

    def test_labor_like_laptev(self):
        c = self._cost(self._newbie("labor"))
        self.assertEqual((c["fixed_net"], c["fixed_cost"]), (15000, 23766))
        amounts = [x["amount"] for x in c["breakdown"]]
        self.assertEqual(amounts, [15000, 19481, 3507, 974, 4285, 23766])
        net, gross, pdfo, vz, esv, total = amounts
        self.assertEqual(gross - pdfo - vz, net)      # утримання з людини сходяться
        self.assertEqual(gross + esv, total)          # + ЄСВ зверху = вартість для компанії
        self.assertEqual(total, c["fixed_cost"])
        self.assertIn("нараховано 19 481", c["breakdown_text"])
        self.assertIn("компанії 23 766 ₴", c["breakdown_text"])
        self.assertEqual(c["fixed_sum"], 12000)
        self.assertIn("оклад за вихід 6 000 + стандарт до 6 000 = 12 000", c["fixed_explain"])
        self.assertIn("діє гарантія 15 000 до 13.11.2026", c["fixed_explain"])
        self.assertIn("більша сума: 15 000", c["fixed_explain"])
        self.assertEqual(c["guarantee_info"]["end"], "2026-11-13")
        self.assertEqual(c["guarantee_info"]["status"], "active")
        self.assertTrue(any("умови виконано" in n for n in c["fixed_notes"]))

    def test_guarantee_ended_is_not_counted(self):
        c = self._cost(self._newbie("labor"), on=date(2026, 12, 1))
        self.assertEqual(c["fixed_net"], 12000)
        self.assertEqual(c["fixed_cost"], round(12000 / 0.77 * 1.22))
        self.assertIn("закінчилась 13.11.2026", c["fixed_explain"])
        self.assertEqual(c["breakdown"][-1]["amount"], c["fixed_cost"])

    def test_fop_compensated(self):
        c = self._cost(self._newbie("fop"))
        self.assertEqual(c["fixed_cost"], round(15000 / 0.95 + 1902))  # 17 691
        amounts = [x["amount"] for x in c["breakdown"]]
        self.assertEqual(amounts, [15000, 15789, 789, 1902, 17691])
        self.assertEqual(amounts[1] - amounts[2], amounts[0])
        self.assertEqual(amounts[1] + amounts[3], amounts[4])
        self.assertIn("ЄСВ ФОП 1 902", c["breakdown_text"])

    def test_fop_not_compensated(self):
        PayPolicy.objects.filter(pk=1).update(params={"replaced_articles": [], "taxes": {"fop_compensate": False}})
        pol = engine.policy()
        c = self._cost(self._newbie("fop"), pol=pol)
        self.assertEqual(c["fixed_cost"], 15000)
        self.assertEqual([x["amount"] for x in c["breakdown"]], [15000, 15000])
        self.assertIn("не компенсує", c["breakdown_text"])

    def test_no_employment(self):
        c = self._cost(self._newbie("none"))
        self.assertEqual((c["fixed_net"], c["fixed_cost"]), (15000, 15000))
        self.assertIn("Без оформлення", c["breakdown_text"])
        self.assertEqual(c["breakdown"][-1]["amount"], 15000)

    def test_zero_fixed(self):
        s = PayScheme.objects.create(position="Таргетолог", valid_from=date(2026, 9, 1), employment="labor")
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", params={"amount": 0})
        c = self._cost(s)
        self.assertEqual((c["fixed_net"], c["fixed_cost"]), (0, 0))
        self.assertEqual(c["breakdown"], [])

    def test_old_numbers_unchanged(self):
        """Усі старі поля scheme_cost — ті самі значення, що давала функція до патчу."""
        U = get_user_model()
        wh = U.objects.create_user("prux-wh", "prux-w@example.test", "x")
        schemes = [self._newbie("labor"), self._newbie("fop", user=U.objects.create_user("prux-2", "p2@example.test", "x")),
                   self._newbie("none", user=U.objects.create_user("prux-3", "p3@example.test", "x"))]
        w = PayScheme.objects.create(user=wh, position="Комірник", department="Склад", valid_from=date(2026, 7, 1), employment="none")
        PayComponent.objects.create(scheme=w, kind="fixed_monthly", params={"amount": 8000})
        PayComponent.objects.create(scheme=w, kind="piece_rate", params={})
        v = PayScheme.objects.create(position="Вакансія салону", valid_from=date(2026, 11, 1), is_vacancy=True, in_plan=False,
                                     employment="labor", planned_start=date(2026, 11, 1))
        PayComponent.objects.create(scheme=v, kind="base_by_days", params={"amount": 7000})
        PayComponent.objects.create(scheme=v, kind="standard", params={"max": 8000})
        PayComponent.objects.create(scheme=v, kind="revenue_share", params={"pct": 2, "basis": "funnels", "funnels": [5]})
        PayComponent.objects.create(scheme=v, kind="guarantee", params={"amount": 15000, "months": 2, "start": "2026-11-01"})
        schemes += [w, v]
        for on in (ON, date(2026, 12, 1), date(2026, 9, 1)):
            for s in schemes:
                new, old = engine.scheme_cost(s, self.pol, self.sh, on), _old_scheme_cost(s, self.pol, self.sh, on)
                for k in OLD_KEYS:
                    self.assertEqual(new[k], old[k], f"{s.position} {on}: {k}")
        vc = engine.scheme_cost(v, self.pol, self.sh, ON)
        self.assertEqual(vc["guarantee_info"]["status"], "vacancy")
        self.assertIn("не більша", vc["fixed_explain"])  # 7 000 + 8 000 = 15 000 = гарантія

    def test_api_schemes_has_breakdown_and_wh_rates(self):
        FinModelArticle.objects.filter(category="warehouse_rate").update(active=False)
        kg = FinModelArticle.objects.create(category="warehouse_rate", name="Відвантаження: ставка за кг", value=Decimal("1.5"),
                                            value_type="fixed_per_deal", code="WH_RATE_KG")
        FinModelArticle.objects.create(category="warehouse_rate", name="Оплата складу за збірку тестового набору", value=Decimal("50"),
                                       value_type="fixed_per_deal", code="bundle_assembly")
        self._newbie("labor")
        c = APIClient()
        c.force_authenticate(self.mgr)
        self.assertEqual(c.get("/api/payroll/schemes/", HTTP_HOST=HOST).status_code, 403)  # права не змінились
        c.force_authenticate(self.owner)
        d = c.get("/api/payroll/schemes/", HTTP_HOST=HOST).json()
        row = next(s for s in d["schemes"] if s["user_id"] == self.mgr.id)
        self.assertTrue(row["cost"]["breakdown"])
        self.assertIn("fixed_explain", row["cost"])
        self.assertTrue(d["can_edit_wh_rates"])
        self.assertEqual([(r["code"], r["auto"]) for r in d["warehouse_rates"]], [("WH_RATE_KG", "yes"), ("bundle_assembly", "no")])
        # одне джерело: змінили статтю Фінмоделі (той самий PATCH, що робить сторінка) → ставки показують нове число
        r = c.patch(f"/api/finmodel-articles/{kg.id}/", {"value": "1.75"}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        d = c.get("/api/payroll/schemes/", HTTP_HOST=HOST).json()
        self.assertEqual(next(x for x in d["warehouse_rates"] if x["id"] == kg.id)["value"], 1.75)
