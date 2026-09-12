"""Тестове посилання на відгук для перевірки форми магазину. Лише воронка «Техническая(Тесты)».

    python manage.py reviews_test_invite --create-test-deal --product 1653            # план (DRY)
    python manage.py reviews_test_invite --create-test-deal --product 1653 --apply    # створити
    python manage.py reviews_test_invite --deal 60980 --apply                         # посилання до наявної тестової угоди

Тестовий контакт — без телефону, тож йому нічого не надсилається. Відгуки з тестових посилань мають
is_test=True і не потрапляють у публічну стрічку магазину (лише з include_test=true).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.crm.models import Contact, Deal, DealItem, Funnel
from apps.reviews.models import ReviewRequest
from apps.reviews.services import new_code, review_link


class Command(BaseCommand):
    help = "Тестове посилання на відгук (лише воронка «Техническая(Тесты)»; без --apply — план)"

    def add_arguments(self, parser):
        parser.add_argument("--deal", type=int)
        parser.add_argument("--create-test-deal", action="store_true")
        parser.add_argument("--product", type=int, action="append", default=[])
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        funnel = Funnel.objects.filter(name__icontains="Техническая").order_by("id").first()
        if funnel is None:
            raise CommandError("Немає воронки «Техническая(Тесты)»")
        with transaction.atomic():
            if opts["deal"]:
                deal = Deal.objects.select_related("contact").filter(pk=opts["deal"]).first()
                if deal is None or deal.funnel_id != funnel.id:
                    raise CommandError("Лише угоди з воронки «%s»" % funnel.name)
            elif opts["create_test_deal"]:
                contact = Contact.objects.create(
                    first_name="ТЕСТ", last_name="Відгуки", source="test",
                    comment="Тестовий контакт для перевірки форми відгуків на сайті. Не клієнт, без телефону — "
                            "повідомлення не надсилаються.")
                deal = Deal.objects.create(title="ТЕСТ · відгуки (не клієнт)", contact=contact, funnel=funnel,
                                           stage=funnel.stages.order_by("order", "id").first(), source="test", amount=0)
                for product_id in opts["product"]:
                    DealItem.objects.create(deal=deal, product_id=product_id, quantity=1, price=0)
                self.stdout.write("  + контакт #%s, угода #%s у «%s», товарів: %s"
                                  % (contact.id, deal.id, funnel.name, len(opts["product"])))
            else:
                raise CommandError("Вкажіть --deal ID або --create-test-deal")
            req = ReviewRequest.objects.create(
                deal=deal, contact=deal.contact, kind="manual", status="test", is_test=True, code=new_code(),
                expires_at=timezone.now() + timedelta(days=60), reason="Тестове посилання для перевірки форми магазину")
            self.stdout.write("  + тестова просьба #%s, код %s → %s" % (req.id, req.code, review_link(req.code)))
            if opts["apply"]:
                self.stdout.write("LIVE: створено")
            else:
                transaction.set_rollback(True)
                self.stdout.write("DRY: нічого не записано (код вище — лише приклад). Запустіть з --apply.")
