"""Завести «Змагання тижня» на Біржі задач (Розвиток v2, 16.09.2026). DRY за замовчуванням.

    python manage.py rozvytok_contests_seed          # показати, що буде заведено (нічого не пише)
    python manage.py rozvytok_contests_seed --live   # завести

Що заводить: напрям «Змагання тижня» у відділі «Продажі» і 3 задачі-призи (ріст «тест → основне», конверсія,
якість дзвінків). Усе НЕАКТИВНЕ на біржі (кнопки «Беру» немає) і ВИМКНЕНЕ в «Розвитку» — вмикає власник.
Ціна призу — «для обговорення»: власник змінює її на Біржі задач. Наявне не чіпає; видалене власником не повертає.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from apps.bounty.models import TaskCategory, TaskOffer
from apps.gamification.contests import CATEGORY_NAME, CONTESTS
from apps.gamification.models import GamSettings

NOTE = "змагання тижня · ціна для обговорення"


def _texts(c):
    how = ("НЕ натискайте «Беру» — ця задача не береться вручну, приз отримує переможець тижня.\n"
           f"Правило: {c['rule']}\n"
           "Тиждень — з понеділка по неділю. Свої цифри — «Розвиток» → «Змагання тижня».\n"
           "Після неділі власник тисне «Нарахувати приз» — сума йде у вашу ЗП рядком «Задачі з біржі».")
    done = ("Переможця визначає CRM за тими ж даними, що й ЗП (оплати, тест-набори, розбори дзвінків). "
            "Нічия — рішення за власником.")
    why = "Тест-набір → основне — головна точка росту продажів; змагання короткі, у кожного свій шанс."
    res = "Більше основних замовлень після тест-наборів і кращі розмови з клієнтами — щотижня."
    return how, done, why, res


class Command(BaseCommand):
    help = "Завести «Змагання тижня» (Біржа задач, неактивні) — DRY за замовчуванням, --live — записати."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")

    def handle(self, *a, **o):
        live = o["live"]
        w = self.stdout.write
        s = GamSettings.get()
        cfg = dict(s.contests or {})
        cat = TaskCategory.objects.filter(department="sales", name=CATEGORY_NAME).first()
        if cat is not None and cat.archived:
            w(f"Напрям «{CATEGORY_NAME}» видалено власником — нічого не заводжу.")
            return
        w(f"Напрям «{CATEGORY_NAME}» (Продажі): " + ("є" if cat else "буде створено"))
        plan = []
        for c in CONTESTS:
            oid = (cfg.get(c["code"]) or {}).get("offer_id")
            o_ = TaskOffer.objects.filter(pk=oid).first() if oid else None
            if o_ is None and cat is not None:
                o_ = TaskOffer.objects.filter(category=cat, title=c["title"]).first()
            if o_ is not None and o_.archived:
                w(f"  · {c['title']}: видалено власником — пропускаю")
                continue
            w(f"  · {c['title']}: " + (f"є (задача #{o_.id}, приз {o_.price} ₴)" if o_ else f"буде створено, приз {c['prize']} ₴, неактивна"))
            plan.append((c, o_))
        if not live:
            w("DRY: нічого не записано. Щоб завести — додайте --live.")
            return
        with transaction.atomic():
            if cat is None:
                order = (TaskCategory.objects.filter(department="sales").aggregate(m=Max("order"))["m"] or 0) + 1
                cat = TaskCategory.objects.create(department="sales", name=CATEGORY_NAME, order=order, active=True)
            for c, o_ in plan:
                if o_ is None:
                    how, done, why, res = _texts(c)
                    order = (TaskOffer.objects.filter(category=cat).aggregate(m=Max("order"))["m"] or 0) + 1
                    o_ = TaskOffer.objects.create(
                        category=cat, title=c["title"], how_to=how, done_criteria=done, why=why, expected_result=res,
                        subtasks=[], proof_type="text", price=Decimal(str(c["prize"])), unit="task", unit_label="",
                        monthly_limit_qty=5, max_per_person=0, max_takers=1, due_days=7, active=False, order=order, note=NOTE)
                cfg[c["code"]] = {"offer_id": o_.id, "enabled": bool((cfg.get(c["code"]) or {}).get("enabled"))}
            s.contests = cfg
            s.save()
        w("LIVE: заведено. Змагання ВИМКНЕНІ — увімкнути: «Розвиток» → «Змагання тижня» (власник).")
