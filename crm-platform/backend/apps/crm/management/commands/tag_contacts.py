# -*- coding: utf-8 -*-
"""Авторозмітка контрагентів: типи (client/supplier/master/staff/partner) + стать.

БЕЗ --commit нічого не пишеться (DRY-RUN за замовчуванням).
  python manage.py tag_contacts                 # тільки показати, що буде
  python manage.py tag_contacts --limit 5 --commit   # тест на 5
  python manage.py tag_contacts --commit        # бойовий прогін
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.crm.models import Contact
from apps.crm.gender import detect_gender


class Command(BaseCommand):
    help = "Авторозмітка типів контрагентів і статі (dry-run за замовчуванням)"

    def add_arguments(self, p):
        p.add_argument("--commit", action="store_true", help="реально записати (без цього — dry-run)")
        p.add_argument("--limit", type=int, default=0, help="обробити не більше N (для тесту)")
        p.add_argument("--only", default="", help="kinds | gender (за замовчуванням обидва)")

    def handle(self, *a, **o):
        commit = o["commit"]
        limit = o["limit"]
        only = o["only"]
        tag = self.style.SUCCESS("LIVE") if commit else self.style.WARNING("DRY-RUN")
        self.stdout.write(f"Режим: {tag}")

        # ── 1) ТИПИ ────────────────────────────────────────────────
        if only in ("", "kinds"):
            from apps.warehouse.models import StockDocument
            from apps.finance.models import PlannedPayment
            from apps.crm.models import Deal

            sup_ids = set(StockDocument.objects.exclude(supplier=None)
                          .values_list("supplier_id", flat=True))
            sup_ids |= set(PlannedPayment.objects.filter(kind="payable").exclude(contact=None)
                           .values_list("contact_id", flat=True))
            cli_ids = set(Deal.objects.exclude(contact=None).values_list("contact_id", flat=True))

            self.stdout.write(f"\nПостачальники (за приходами/кредиторкою): {len(sup_ids)}")
            self.stdout.write(f"Клієнти (мають угоду): {len(cli_ids)}")

            changed = 0
            # ⚠️ Постачальників авто-НЕ проставляємо — тип ставить Олег руками в картці.
            for cid, kind in [(cli_ids, "client")]:
                qs = Contact.objects.filter(id__in=cid)
                if limit:
                    qs = qs[:limit]
                for c in qs:
                    kinds = list(c.kinds or [])
                    if kind in kinds:
                        continue
                    kinds.append(kind)
                    changed += 1
                    if changed <= 10:
                        self.stdout.write(f"   + {kind}: {c} (було {c.kinds or []})")
                    if commit:
                        c.kinds = kinds
                        c.save(update_fields=["kinds"])
            self.stdout.write(self.style.SUCCESS(f"Типів проставлено: {changed}"))

        # ── 2) СТАТЬ ───────────────────────────────────────────────
        if only in ("", "gender"):
            qs = Contact.objects.filter(gender="").exclude(
                Q(first_name="") & Q(middle_name="") & Q(last_name=""))
            total = qs.count()
            if limit:
                qs = qs[:limit]
            stat = {"m": 0, "f": 0, "": 0}
            src_stat = {}
            shown = 0
            for c in qs.iterator(chunk_size=2000):
                g, src = detect_gender(c.first_name, c.middle_name, c.last_name)
                stat[g] = stat.get(g, 0) + 1
                if g:
                    src_stat[src] = src_stat.get(src, 0) + 1
                    if shown < 12:
                        self.stdout.write(f"   {('ЧОЛ' if g=='m' else 'ЖІН')}: {c.first_name} {c.middle_name} {c.last_name}".rstrip() + f"  ← {src}")
                        shown += 1
                    if commit:
                        c.gender = g
                        c.save(update_fields=["gender"])
            self.stdout.write(f"\nБез статі зараз: {total}")
            self.stdout.write(self.style.SUCCESS(
                f"Визначено: ЧОЛ {stat.get('m',0)} | ЖІН {stat.get('f',0)} | не вдалося (нік/латиниця) {stat.get('',0)}"))
            self.stdout.write(f"Джерела: {src_stat}")

        if not commit:
            self.stdout.write(self.style.WARNING("\nЦе був DRY-RUN — нічого не записано. Додай --commit."))
