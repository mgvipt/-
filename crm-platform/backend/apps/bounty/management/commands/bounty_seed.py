"""Завести / оновити прайс біржі задач Wallcov (seed_data.SEED — v2 від 15.09.2026).

    python manage.py bounty_seed --dry              # показати, що буде заведено (нічого не пише)
    python manage.py bounty_seed                    # завести відсутні напрями і задачі; наявні НЕ чіпає
    python manage.py bounty_seed --update --dry     # показати оновлення задач v1 → v2 (нічого не пише)
    python manage.py bounty_seed --update           # + переписати задачі, яких власник НЕ змінював

Правила (обидва режими):
- напрям шукаємо за (відділ, назва); задачу — за (напрям, назва з прайсу 14.09) або (напрям, нова назва), з видаленими;
- видалене власником (архів) не повертаємо і не змінюємо;
- нічого не видаляємо, нічого не вмикаємо і не вимикаємо; «хто приймає» і порядок наявних задач не чіпаємо;
- усе нове — НЕАКТИВНЕ з приміткою «ціна для обговорення».
Лише --update:
- «змінено власником» = назва / «як виконати» / «що вважається виконаним» відрізняються від заведених 14.09
  (seed_v1.py) → задачу пропускаємо ЦІЛКОМ і показуємо в списку;
- «навіщо», «кінцевий результат», підзадачі — заповнюємо, лише якщо порожні;
- ціну, одиницю, ліміти, термін, доказ міняємо, лише якщо вони рівно як 14.09; інакше лишаємо власникові (у списку);
- примітку міняємо, лише якщо вона рівно «ціна для обговорення».
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from apps.bounty.models import DEPARTMENT_LABELS, TaskCategory, TaskOffer
from apps.bounty.seed_data import NOTE, SEED
from apps.bounty.seed_v1 import NOTE as NOTE_V1
from apps.bounty.seed_v1 import SEED as SEED_V1
from apps.bounty.services import unit_text

TEXT = ("title", "how_to", "done_criteria")
NEW = ("why", "expected_result", "subtasks")
NUM = ("price", "unit", "unit_label", "monthly_limit_qty", "max_per_person", "max_takers", "due_days", "proof_type")
LABELS = {"title": "назва", "how_to": "як виконати", "done_criteria": "що вважається виконаним", "price": "ціна",
          "unit": "одиниця", "unit_label": "штука", "monthly_limit_qty": "ліміт", "max_per_person": "на людину",
          "max_takers": "людей одночасно", "due_days": "термін", "proof_type": "доказ"}
V1 = {(dep, cat, o["title"]): o for dep, cat, offers in SEED_V1 for o in offers}


def _n(v):
    if isinstance(v, Decimal):
        return v.quantize(Decimal("0.01"))
    if isinstance(v, float) or (isinstance(v, int) and not isinstance(v, bool)):
        return v
    return str(v or "").replace("\r\n", "\n").strip()


def _seed(d, f):
    return Decimal(str(d[f])).quantize(Decimal("0.01")) if f == "price" else _n(d[f])


def _same(o, d, fields):
    return all(_n(getattr(o, f)) == _seed(d, f) for f in fields)


def _diff(o, d, fields):
    return [LABELS[f] for f in fields if _n(getattr(o, f)) != _seed(d, f)]


def _num_value(d, f):
    return Decimal(str(d[f])) if f == "price" else d[f]


class Command(BaseCommand):
    help = ("Біржа задач: завести прайс Wallcov (усе нове НЕактивне). --update — переписати задачі 14.09, "
            "яких власник не змінював. --dry — лише показати.")

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true", help="Нічого не писати, лише показати")
        parser.add_argument("--update", action="store_true", help="Оновити незмінені власником задачі до v2")

    def handle(self, *args, **opts):
        dry, upd = opts["dry"], opts["update"]
        c = {"new_c": 0, "new_o": 0, "had": 0, "updated": 0, "current": 0, "edited": 0, "deleted": 0, "kept_num": 0}
        edited, kept = [], []
        w = self.stdout.write
        with transaction.atomic():
            for dep, cat_name, offers in SEED:
                cat = TaskCategory.objects.filter(department=dep, name=cat_name).order_by("archived", "id").first()
                head = f"[{DEPARTMENT_LABELS.get(dep, dep)} · {cat_name}]"
                if cat and cat.archived:
                    c["deleted"] += len(offers)
                    w(f"  {head} напрям видалено власником — пропускаю {len(offers)} задач")
                    continue
                if not cat:
                    c["new_c"] += 1
                    w(f"+ {head} новий напрям")
                    if not dry:
                        m = TaskCategory.objects.filter(department=dep).aggregate(m=Max("order"))["m"] or 0
                        cat = TaskCategory.objects.create(department=dep, name=cat_name, order=m + 10, active=True)
                for d in offers:
                    self._one(cat, head, dep, cat_name, d, dry, upd, c, edited, kept)
            if dry:
                transaction.set_rollback(True)
        mode = "ПЕРЕВІРКА (--dry), нічого не записано" if dry else ("ОНОВЛЕНО" if upd else "ЗАВЕДЕНО")
        if edited:
            w("\nЗмінені власником — НЕ чіпаю (переглянути вручну):")
            for oid, title, fields in edited:
                w(f"  #{oid} {title}: відрізняється {', '.join(fields)}")
        if kept:
            w("\nЦіни/ліміти власника лишаю як є (тексти оновлено):")
            for oid, title, fields in kept:
                w(f"  #{oid} {title}: {', '.join(fields)}")
        tail = (f", оновлено {c['updated']}, уже актуальні {c['current']}, змінено власником — пропущено {c['edited']}, "
                f"ціни/ліміти власника лишено {c['kept_num']}") if upd else f", уже було {c['had']}"
        w(f"\n{mode}: нових напрямів {c['new_c']}, нових задач {c['new_o']}{tail}, видалено власником — пропущено "
          f"{c['deleted']}. Нове — НЕАКТИВНЕ («{NOTE}»); нічого не ввімкнено і не видалено.")

    def _one(self, cat, head, dep, cat_name, d, dry, upd, c, edited, kept):
        w = self.stdout.write
        price = unit_text(d["unit"], d["unit_label"], Decimal(str(d["price"])))
        limit = f", ліміт {d['monthly_limit_qty']}/міс" if d["monthly_limit_qty"] else ""
        line = f"{head} {d['title']} — {price}{limit}"
        o = None
        if cat is not None and cat.pk:
            if d.get("v1_title"):
                o = TaskOffer.objects.filter(category=cat, title=d["v1_title"]).order_by("id").first()
            if o is None:
                o = TaskOffer.objects.filter(category=cat, title=d["title"]).order_by("id").first()
        if o is None:
            c["new_o"] += 1
            w(f"+ {line} ({len(d['subtasks'])} підзадач)" + (f" · {d['flag']}" if d["flag"] else ""))
            if not dry:
                m = TaskOffer.objects.filter(category=cat).aggregate(m=Max("order"))["m"] or 0
                TaskOffer.objects.create(
                    category=cat, title=d["title"], how_to=d["how_to"], done_criteria=d["done_criteria"],
                    why=d["why"], expected_result=d["expected_result"], subtasks=d["subtasks"],
                    proof_type=d["proof_type"], price=Decimal(str(d["price"])), unit=d["unit"], unit_label=d["unit_label"],
                    monthly_limit_qty=d["monthly_limit_qty"], max_per_person=d["max_per_person"],
                    max_takers=d["max_takers"], due_days=d["due_days"], active=False, note=d["note"], order=m + 10)
            return
        if o.archived:
            c["deleted"] += 1
            w(f"  {line} — видалено власником, не чіпаю")
            return
        if not upd:
            c["had"] += 1
            w(f"= {line} (вже є)")
            return
        v1 = V1.get((dep, cat_name, d["v1_title"])) if d.get("v1_title") else None
        if _same(o, d, TEXT):
            text_state = "v2"
        elif v1 and _same(o, v1, TEXT):
            text_state = "v1"
        else:
            c["edited"] += 1
            edited.append((o.id, o.title, _diff(o, v1 or d, TEXT)))
            w(f"! #{o.id} {o.title} — змінено власником, пропускаю")
            return
        ch = {}
        if text_state == "v1":
            ch.update({f: d[f] for f in TEXT})
        for f in NEW:
            if not getattr(o, f) and d[f]:
                ch[f] = d[f]
        if not _same(o, d, NUM):
            if v1 and _same(o, v1, NUM):
                ch.update({f: _num_value(d, f) for f in NUM if _n(getattr(o, f)) != _seed(d, f)})
            else:
                c["kept_num"] += 1
                kept.append((o.id, o.title, _diff(o, v1 or d, NUM)))
        if o.note.strip() in (NOTE_V1, NOTE, "") and o.note != d["note"]:
            ch["note"] = d["note"]
        if not ch:
            c["current"] += 1
            return
        c["updated"] += 1
        what = ", ".join(LABELS.get(f, {"why": "навіщо", "expected_result": "результат", "subtasks": "підзадачі",
                                        "note": "примітка"}.get(f, f)) for f in ch)
        w(f"~ #{o.id} {line}: {what}")
        if not dry:
            for f, v in ch.items():
                setattr(o, f, v)
            o.save(update_fields=[*ch, "updated_at"])
