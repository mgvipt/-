"""Завести прайс біржі задач Wallcov (seed_data.SEED).

    python manage.py bounty_seed --dry     # лише показати, що буде заведено (нічого не пише)
    python manage.py bounty_seed           # завести

Ідемпотентно: напрям шукаємо за (відділ, назва), задачу — за (напрям, назва), разом з ВИДАЛЕНИМИ (архів):
видалене власником повторний запуск НЕ повертає. Усе нове — НЕАКТИВНЕ з приміткою «ціна для обговорення».
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.bounty.models import DEPARTMENT_LABELS, TaskCategory, TaskOffer
from apps.bounty.seed_data import NOTE, SEED
from apps.bounty.services import unit_text


class Command(BaseCommand):
    help = "Біржа задач: завести прайс задач Wallcov (усі НЕактивні, «ціна для обговорення»). --dry — лише показати."

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true", help="Нічого не писати, лише показати список")

    def handle(self, *args, **opts):
        dry = opts["dry"]
        new_c = new_o = had_o = skipped = 0
        order_in_dep = {}
        with transaction.atomic():
            for dep, cat_name, offers in SEED:
                order_in_dep[dep] = order_in_dep.get(dep, 0) + 10
                cat = TaskCategory.objects.filter(department=dep, name=cat_name).order_by("archived", "id").first()
                head = f"[{DEPARTMENT_LABELS.get(dep, dep)} · {cat_name}]"
                if cat and cat.archived:
                    skipped += len(offers)
                    self.stdout.write(f"  {head} напрям видалено власником — пропускаю {len(offers)} задач")
                    continue
                if not cat:
                    new_c += 1
                    if not dry:
                        cat = TaskCategory.objects.create(department=dep, name=cat_name, order=order_in_dep[dep], active=True)
                for i, o in enumerate(offers):
                    exists = bool(cat and cat.pk and TaskOffer.objects.filter(category=cat, title=o["title"]).exists())
                    limit = f", ліміт {o['monthly_limit_qty']}/міс" if o["monthly_limit_qty"] else ""
                    line = f"{head} {o['title']} — {unit_text(o['unit'], o['unit_label'], Decimal(str(o['price'])))}{limit}"
                    if exists:
                        had_o += 1
                        self.stdout.write(f"= {line} (вже є)")
                        continue
                    new_o += 1
                    self.stdout.write(f"+ {line}")
                    if not dry:
                        TaskOffer.objects.create(
                            category=cat, title=o["title"], how_to=o["how_to"], done_criteria=o["done_criteria"],
                            proof_type=o["proof_type"], price=Decimal(str(o["price"])), unit=o["unit"],
                            unit_label=o["unit_label"], monthly_limit_qty=o["monthly_limit_qty"],
                            max_per_person=o["max_per_person"], max_takers=o["max_takers"], due_days=o["due_days"],
                            active=False, note=NOTE, order=(i + 1) * 10)
            if dry:
                transaction.set_rollback(True)
        mode = "ПЕРЕВІРКА (--dry), нічого не записано" if dry else "ЗАВЕДЕНО"
        self.stdout.write(f"\n{mode}: нових напрямів {new_c}, нових задач {new_o}, уже було {had_o}, пропущено {skipped}. "
                          f"Усі нові задачі — НЕАКТИВНІ («{NOTE}»).")
