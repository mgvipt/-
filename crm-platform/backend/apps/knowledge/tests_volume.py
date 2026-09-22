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
        self.assertIn("Разом з тонуванням", block)

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
    """Регламент Wallcov (Notion, 27.07.2025): фактурні <5 кг — 100 грн, ≥5 кг — кг×20;
    тонкошарові — 100 грн за тару; тонер 6 грн/мл."""
    def _calc(self, base, qty, unit="кг"):
        return {"ok": True, "base": base, "material": {"qty": Decimal(qty), "unit": unit}}

    def test_facture_small_and_big(self):
        t = vc.tint_estimate(self._calc("facture", "3"))
        self.assertEqual(t["service"], Decimal("100.00"))
        self.assertEqual(t["ml"], Decimal("12"))          # 3 кг × 4 мл
        self.assertEqual(t["total"], Decimal("172.00"))   # приклад із регламенту
        t2 = vc.tint_estimate(self._calc("facture", "8"))
        self.assertEqual(t2["service"], Decimal("160.00"))
        self.assertEqual(t2["total"], Decimal("352.00"))  # 160 + 32 мл × 6

    def test_thin_per_tara(self):
        t = vc.tint_estimate(self._calc("thin", "6.5"))
        self.assertEqual(t["tara"], 2)
        self.assertEqual(t["service"], Decimal("200.00"))

    def test_rich_color_more_toner(self):
        self.assertEqual(vc.tint_estimate(self._calc("facture", "10"), rich=True)["ml"], Decimal("100"))

    def test_pieces_not_tinted(self):
        self.assertIsNone(vc.tint_estimate(self._calc("facture", "2", "шт")))
