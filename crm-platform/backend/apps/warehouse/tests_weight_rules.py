"""15.09.2026: регламент ваги/упаковки v2 — чисті перевірки правила на прикладах Олега (без БД)."""
from decimal import Decimal

from django.test import SimpleTestCase

from . import weight_rules as WR


def it(name, unit="шт", qty=1, card_w=None, **kw):
    return dict(name=name, unit=unit, qty=Decimal(str(qty)), card_w=None if card_w is None else Decimal(str(card_w)), **kw)


class WeightRulesV2Tests(SimpleTestCase):
    def test_test_set_is_quarter_kg_and_one_parcel_up_to_5(self):
        # #66733 Мокляр: 2 тест-набори з вагою в картці 5 і 3 кг → 0,5 кг і одна посилка до 5 кг (не «до 10»)
        p = WR.plan([it("Sirena Silk — тестовий набір «Мокрий шовк»", card_w=5, is_kit=True),
                     it("Sirena Silk — тестовий набір «Мокрий шовк» з тонуванням", card_w=3, is_kit=True)])
        self.assertEqual(p["weight"], Decimal("0.500"))
        self.assertEqual(p["tiers"], {"T5": 1, "T10": 0, "T20": 0})

    def test_kg_unit_weight_is_quantity_and_repacked_portions(self):
        # #66719 Бекшанова: Velvet Luna 0,6 кг + Sirena Silk 5,3 кг + тара + тонування
        p = WR.plan([it("Velvet Luna (Str 0501) Silver", "кг", "0.6"), it("Послуга тонування", is_tint=True),
                     it("Тара 1л"), it("Тара 5,5л"), it("Sirena Silk ( ChS 0201 ), Silver,12кг. Шовковий", "кг", "5.3")])
        self.assertEqual(p["weight"], Decimal("5.900"))
        self.assertEqual(p["tiers"], {"T5": 1, "T10": 1, "T20": 0})

    def test_full_factory_bucket_not_packed(self):
        p = WR.plan([it("Pattera Micro (FB 0101), 16кг. Декоративна", "кг", 22.5)])
        self.assertEqual(p["weight"], Decimal("22.500"))
        self.assertEqual(p["tiers"], {"T5": 0, "T10": 1, "T20": 0})  # 1 відро 16 кг — не пакуємо; 6,5 кг → до 10

    def test_card_weight_of_kg_product_is_not_multiplied(self):
        p = WR.plan([it("Sirena Silk Bianco", "кг", 3, card_w=5)])
        self.assertEqual(p["weight"], Decimal("3.000"))

    def test_large_piece_uses_card_weight(self):
        # #66568: карниз Orac C213 × 10; після виправлення картки 1,5 кг → 15 кг, одне місце до 20
        p = WR.plan([it("C213 карниз Orac Luxxus 200 x 8 x 8", qty=10, card_w="1.5")])
        self.assertEqual(p["weight"], Decimal("15.000"))
        self.assertEqual(p["tiers"], {"T5": 0, "T10": 0, "T20": 1})
        p0 = WR.plan([it("Люк ревізійний 60×60", qty=1)])
        self.assertEqual(p0["weight"], Decimal("0.000"))
        self.assertEqual(len(p0["weightless"]), 1)

    def test_tools_one_box_min_half_kg(self):
        p = WR.plan([it("Валик Velurplus 10 см, ворс 4 мм"), it("Ручка для валика Vist 8мм * 100 мм"),
                     it("Шпатель Профі, Favorit 60мм")])
        self.assertEqual(p["weight"], Decimal("0.500"))  # 0,03 + 0,1 + 0,06 = 0,19 → не менше 0,5
        self.assertEqual(p["tiers"], {"T5": 1, "T10": 0, "T20": 0})

    def test_samples_zero_weight_one_parcel(self):
        p = WR.plan([it("Викраски 10/30", qty=3)])
        self.assertEqual(p["weight"], Decimal("0.000"))
        self.assertEqual(p["tiers"], {"T5": 1, "T10": 0, "T20": 0})

    def test_salon_without_ttn_no_packing(self):
        p = WR.plan([it("Second Layer (FL 1006),15кг", "кг", 5), it("Sirena Silk, 12кг", "кг", "3.75")], salon=True)
        self.assertEqual(p["weight"], Decimal("8.750"))
        self.assertEqual(p["tiers"], {"T5": 0, "T10": 0, "T20": 0})

    def test_toner_in_ml_not_pieces(self):
        # #66731: тонер CSK з одиницею «шт», к-сть 20 і 40 — це мілілітри (60 мл ≈ 0,09 кг), а не 6 кг дрібниць
        p = WR.plan([it("Тонер/Toner CSK09(Світло коричневий) мл", qty=20), it("Тонер/Toner CSK09(Світло коричневий) мл", qty=40),
                     it("Тара 0,01л ( Шприц 10 мл)", qty=6)])
        self.assertEqual(p["weight"], Decimal("0.090"))
        self.assertEqual(p["tiers"], {"T5": 1, "T10": 0, "T20": 0})

    def test_bottle_and_100ml(self):
        p = WR.plan([it("Protection D MAT +( DC-U 1009)", "л", 2), it("Primer Deep 1 (UPr XZ 1001_100 )", qty=3)])
        self.assertEqual(p["weight"], Decimal("2.300"))   # 2 л × 1,0 + 3 × 0,1
        self.assertEqual(p["tiers"], {"T5": 2, "T10": 0, "T20": 0})  # пляшка до 5 + коробка дрібниць до 5
