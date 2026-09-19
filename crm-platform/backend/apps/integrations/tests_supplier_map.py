"""19.09.2026: автопідстановка товару в прихід — правило за постачальником, а не за іменем файлу."""
from django.test import TestCase

from apps.crm.models import Contact
from apps.warehouse.models import Product

from .models import SupplierProductMap, find_rules, norm_name, supplier_key_for


class SupplierMapTests(TestCase):
    def setUp(self):
        self.sup = Contact.objects.create(first_name="Прана Україна", kinds=["supplier"], edrpou="12345678")
        self.p = Product.objects.create(name='Рекуператор Prana 150 стандарт', unit="шт")

    def test_manual_upload_rule_found_next_time(self):
        # старе правило під імʼям файлу (так писалось до 19.09) — все одно знаходиться за назвою
        SupplierProductMap.objects.create(supplier_key="ручне завантаження · рахунок_№_1169.pdf",
                                          their_name="Припливно-витяжна система PRANA-150 Standart", product=self.p)
        r = find_rules(["Припливно-витяжна система  PRANA-150 Standart"], contact=self.sup,
                       legacy_key="ручне завантаження · рахунок_№_2000.pdf")
        self.assertEqual(r["Припливно-витяжна система  PRANA-150 Standart"].product_id, self.p.id)

    def test_new_rules_are_keyed_by_supplier(self):
        self.assertEqual(supplier_key_for(self.sup), "contact:%s" % self.sup.id)
        SupplierProductMap.objects.create(supplier_key=supplier_key_for(self.sup), their_name="PRANA-150 Standart", product=self.p)
        self.assertIn("prana-150 standart", {norm_name(x) for x in find_rules(["«PRANA-150 Standart»"], self.sup)})

    def test_catalog_import_rules_not_used_across_suppliers(self):
        SupplierProductMap.objects.create(supplier_key="grafio-catalog-source-id", their_name="PRANA-150", product=self.p)
        self.assertEqual(find_rules(["PRANA-150"], contact=None, legacy_key="x@y.ua"), {})
