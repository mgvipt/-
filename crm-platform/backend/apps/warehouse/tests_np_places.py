"""19.09.2026: місця/вага з Нової Пошти, таблиця «як пораховано»."""
from django.test import SimpleTestCase

from apps.payroll.detail_views import how_rows

from .np_places import per_seat, tiers_for


class NpPlacesTests(SimpleTestCase):
    def test_our_seats_used_when_they_match_np(self):
        w, src = per_seat({"seats": 2, "weight": 3.8}, [{"kg": "1.610"}, {"kg": "1.870"}])
        self.assertEqual((w, src), ([1.61, 1.87], "ТТН CRM"))

    def test_estimate_when_our_seats_differ(self):
        w, src = per_seat({"seats": 3, "weight": 10.68}, [{"kg": 5}])
        self.assertEqual(w, [3.56, 3.56, 3.56])
        self.assertTrue(src.startswith("оцінка"))

    def test_tiers_by_weight(self):
        self.assertEqual(tiers_for([5.52]), {"T5": 0, "T10": 1, "T20": 0})   # #66790: 5,52 кг → до 10 кг
        self.assertEqual(tiers_for([1.61, 1.87]), {"T5": 2, "T10": 0, "T20": 0})

    def test_how_rows_table(self):
        rows = how_rows(["Мокрий шовк 5 кг — відро 5 кг", "  заводське відро 5 кг → упаковка до 5 кг",
                         "  інструменти/дрібниці разом 0,3 кг → рахуємо 0,5 кг (не менше 0,5, не більше 5)"])
        self.assertEqual([r["kind"] for r in rows], ["item", "place", "note"])
        self.assertEqual(rows[1]["detail"], "місце до 5 кг")
