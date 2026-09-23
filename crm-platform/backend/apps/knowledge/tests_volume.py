# -*- coding: utf-8 -*-
"""22.09.2026: продавець CRM рахує обʼєм з карток каталогу; підхоплює чат після «передала менеджеру» (і російською)."""
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.inbox.ai_reply import BUY_RX, HANDOFF_RX
from apps.knowledge import volume_calc as vc


class PhrasesTests(TestCase):
    def test_handoff_ru_ua(self):
        for t in ("Передала Ваш запрос менеджеру: подготовят точный расчёт", "Передала дані менеджеру",
                  "Менеджер свяжется с Вами", "менеджер надішле посилання", "Передаю менеджеру"):
            self.assertTrue(HANDOFF_RX.search(t), t)
        self.assertFalse(HANDOFF_RX.search("Готовлю этот вариант?"))

    def test_buy_ru(self):
        for t in ("На 10 м давайте сразу", "давайте сразу", "оформляйте", "Хочу заказать", "давайте на 12 м²"):
            self.assertTrue(BUY_RX.search(t), t)
        self.assertFalse(BUY_RX.search("Хочу патеру"))


class FindTests(TestCase):
    def test_area(self):
        self.assertEqual(vc.find_area(["Хочу патеру", "Мне нужно на 10 м2"]), 10)
        self.assertEqual(vc.find_area(["на 12,5 кв"]), 12.5)
        self.assertEqual(vc.find_area(["На 10 м давайте сразу"]), 10)
        self.assertIsNone(vc.find_area(["дощечка 40×40 см", "300 г"]))

    def test_material_latest_wins(self):
        msgs = ["Хочу патеру", "Тогда подойдёт Травертин Pattera Fine", "На 10 м давайте сразу"]
        self.assertEqual(vc.find_material(msgs), (1639, "facture"))
        self.assertEqual(vc.find_material(["вельвет люкс"]), (1650, "facture"))
        self.assertEqual(vc.find_material(["Вельвет Луна золото"]), (1648, "velvet_luna"))
        self.assertEqual(vc.find_material(["гротто на кварці"]), (1641, "facture"))
        self.assertEqual(vc.find_material(["скільки на 10 м"], "Галатея"), (1623, "thin"))
        self.assertIsNone(vc.find_material(["скільки на 10 м"]))


class EstimateTests(TestCase):
    def _p(self, pid, name, price, unit, cons):
        from apps.warehouse.models import Product
        return Product.objects.create(id=pid, name=name, price=Decimal(price), unit=unit,
                                      consumption_per_m2=(Decimal(cons) if cons else None))

    def test_pie_from_catalog_cards(self):
        self._p(1639, "Pattera Fine (FF 0102) , 16кг. Декоративний", "210", "кг", "1.2")
        self._p(1927, "Primer Deep 1 (UPr XZ 1001_100 )_Універсальний", "80", "шт", "0.17")
        self._p(1582, "Quartz Primer 2,(1002). Грунт з кварцовим наповнювачем.", "200", "кг", "0.2")
        c = vc.estimate(1639, "facture", 10)
        self.assertTrue(c["ok"])
        q = {l["product_id"]: l["qty"] for l in c["lines"]}
        self.assertEqual(q, {1639: Decimal("12"), 1927: Decimal("2"), 1582: Decimal("2")})
        self.assertEqual(c["total"], Decimal("2520") + Decimal("160") + Decimal("400"))
        block = vc.prompt_block(c)
        self.assertIn("Разом: 3080 грн", block)
        self.assertIn("ТОНУВАННЯ", block)
        self.assertIn("КОДОМ КОЛЬОРУ", block)

    def test_missing_consumption_not_invented(self):
        self._p(1649, "Velvet Luna (Str 0501) Silver. Мілкозерниста", "710", "кг", "0.33")
        self._p(1572, "Fondo Decoro(1014). грунт-фарба", "200", "кг", None)
        c = vc.estimate(1649, "velvet_luna", 10)
        self.assertEqual([l["product_id"] for l in c["lines"]], [1649])
        self.assertEqual(len(c["missing"]), 1)
        self.assertIn("Не пораховано", vc.prompt_block(c))

    def test_no_material_consumption_no_calc(self):
        self._p(1640, "Pattera Grose (FK 0103), 16кг.", "210", "кг", None)
        self.assertFalse(vc.estimate(1640, "facture", 10)["ok"])
        self.assertEqual(vc.prompt_block(vc.estimate(1640, "facture", 10)), "")


class SellerVolumeOrderTests(TestCase):
    def _finish(self, reply_json, allowed):
        from apps.knowledge.answer import _finish_seller
        res = {}
        resp = {"content": [{"type": "text", "text": reply_json}]}
        _finish_seller(res, resp, [{"role": "client", "text": "давайте сразу"}], {"allowed": allowed}, [])
        return res

    def test_volume_order_only_with_crm_calc(self):
        j = '{"reply": "Оформлюю: разом 3080 грн", "handoff": false, "order": {"volume": true, "tint": true}}'
        ok = self._finish(j, "РОЗРАХУНОК CRM ... Разом: 3080 грн")
        self.assertEqual(ok.get("order"), {"volume": True, "tint": True})
        self.assertFalse(ok.get("handoff"))
        bad = self._finish(j, "база без розрахунку")
        self.assertIsNone(bad.get("order"))


class GuardsTests(TestCase):
    def test_language_hint(self):
        self.assertIn("РОСІЙСЬКОЮ", vc.language_hint("На 10 м давайте сразу"))
        self.assertEqual(vc.language_hint("Скільки коштує на 10 м?"), "")

    def test_order_only_after_client_saw_total(self):
        calc = {"ok": True, "total": Decimal("3080")}
        before = [{"role": "client", "text": "На 10 м давайте сразу"}]
        self.assertFalse(vc.shown_to_client(before, calc))
        after = [{"role": "agent", "text": "Разом: 3080 грн"}, {"role": "client", "text": "оформляйте"}]
        self.assertTrue(vc.shown_to_client(after, calc))


class TintTests(TestCase):
    """Регламент Wallcov (Notion 27.07.2025) + формула кольору (Олег 22.09.2026):
    друга цифра коду — мл колоранта на 250 г; на 1 кг ×4."""
    def _calc(self, base, qty, unit="кг", podkl=None):
        """Тонуємо матеріал І підкладку (Quartz / Fondo / Second Layer); Primer Deep — ні."""
        lines = [{"product_id": 1639, "short": "Матеріал", "qty": Decimal(qty), "unit": unit},
                 {"product_id": vc.PRIMER_DEEP, "short": "Primer Deep 1", "qty": Decimal("2"), "unit": "шт"}]
        if podkl:
            lines.append({"product_id": 1582, "short": "Підкладка", "qty": Decimal(podkl), "unit": "кг"})
        return {"ok": True, "base": base, "lines": lines,
                "material": {"qty": Decimal(qty), "unit": unit}}

    def test_dose_from_color_code(self):
        self.assertEqual(vc.color_dose("1"), Decimal("1"))
        self.assertEqual(vc.color_dose("20"), Decimal("20"))
        self.assertEqual(vc.color_dose("05"), Decimal("0.5"))
        self.assertEqual(vc.color_dose("1,5"), Decimal("1.5"))     # як у бібліотеці: FBK16-1,5
        self.assertEqual(vc.color_dose("0,05"), Decimal("0.05"))

    def test_toner_by_color(self):
        c = self._calc("facture", "10")
        t1 = vc.tint_estimate(c, Decimal("1"))       # 03-1 → 4 мл/кг
        self.assertEqual(t1["ml"], Decimal("40.0"))
        self.assertEqual(t1["toner"], Decimal("240.00"))
        self.assertEqual(t1["service"], Decimal("200.00"))
        self.assertEqual(t1["total"], Decimal("440.00"))
        t2 = vc.tint_estimate(c, Decimal("20"))      # 03-20 → 80 мл/кг
        self.assertEqual(t2["ml"], Decimal("800.0"))
        t3 = vc.tint_estimate(c, Decimal("0.5"))     # 03-05 → 2 мл/кг
        self.assertEqual(t3["ml"], Decimal("20.0"))

    def test_podkladka_tinted_too(self):
        """Олег 22.09.2026: «так само тонується і підкладка (кварц-ґрунт, фондо або секонд)»."""
        t = vc.tint_estimate(self._calc("facture", "10", podkl="4"), Decimal("1"))
        self.assertEqual(t["kg"], Decimal("14"))         # 10 матеріалу + 4 підкладки
        self.assertEqual(t["ml"], Decimal("56.0"))       # 14 кг × 4 мл
        self.assertEqual(t["service"], Decimal("280.00"))
        self.assertNotIn("Primer Deep", t["what"])       # ґрунт-концентрат не тонується

    def test_thin_tara_per_position(self):
        t = vc.tint_estimate(self._calc("thin", "2.3", podkl="3"), Decimal("1"))
        self.assertEqual(t["tara"], 2)                    # матеріал + підкладка
        self.assertEqual(t["service"], Decimal("200.00"))

    def test_without_color_no_toner_sum(self):
        t = vc.tint_estimate(self._calc("facture", "10"))
        self.assertTrue(t["need_color"])
        self.assertIsNone(t["toner"])

    def test_thin_big_volume_two_tara(self):
        t = vc.tint_estimate(self._calc("thin", "6.5"), Decimal("1"))
        self.assertEqual(t["tara"], 2)                    # 6,5 кг матеріалу = дві тари
        self.assertEqual(t["service"], Decimal("200.00"))

    def test_find_color_in_dialog(self):
        msgs = [{"role": "client", "text": "на 10 м2 патера"}, {"role": "agent", "text": "палітра 01-21"},
                {"role": "client", "text": "колір 03-12, оформляйте"}]
        self.assertEqual(vc.find_color(msgs), ("03-12", Decimal("12"), False))   # немає в бібліотеці — код клієнта
        self.assertIsNone(vc.find_color([{"role": "client", "text": "дощечка 40-40 см це багато тексту про розмір"}]))

    def test_compound_color_code_goes_to_manager(self):
        c = vc.find_color([{"role": "client", "text": "колір FBK20/08-0,15/2,5"}])
        self.assertEqual(c[0], "FBK20/08-0,15/2,5")
        self.assertIsNone(c[1])      # два шари — суму рахує менеджер

    def test_color_from_library(self):
        from apps.inbox.models import MediaLibraryItem
        MediaLibraryItem.objects.create(title="Травертин", section="colors", material="Патера", color_code="FBK16-1,5")
        self.assertEqual(vc.find_color([{"role": "client", "text": "колір 16-1,5"}], 1639),
                         ("FBK16-1,5", Decimal("1.5"), True))

    def test_pieces_not_tinted(self):
        self.assertIsNone(vc.tint_estimate(self._calc("facture", "2", "шт"), Decimal("1")))


class TaraTests(TestCase):
    """23.09.2026 (Олег): «тару рахувати за щільністю» — літри = вага ÷ щільність,
    беремо найменшу тару з каталогу, в яку влазить."""
    def setUp(self):
        from apps.warehouse.models import Product
        for n, name in ((1, "Тара 1л"), (2.2, "ТАРА 2,2"), (3.4, "Тара 3.4л"), (5.5, "Тара 5,5л"), (10, "Тара 10л")):
            Product.objects.create(name=name, price=Decimal("10"), unit="шт")

    def test_tara_by_density(self):
        self.assertEqual(vc.tara_for(Decimal("2.3"), Decimal("1.2"))[:2], (1, "2.2 л"))   # 1,92 л
        self.assertEqual(vc.tara_for(Decimal("8.5"), Decimal("1.5"))[:2], (1, "10 л"))    # 5,67 л
        self.assertEqual(vc.tara_for(Decimal("40"), Decimal("1.5"))[0], 3)                 # 26,7 л → 3 × 10 л

    def test_without_density_fallback(self):
        n, label, by_density = vc.tara_for(Decimal("12"), None)
        self.assertEqual((n, by_density), (3, False))   # запасний варіант: 5 кг на тару
