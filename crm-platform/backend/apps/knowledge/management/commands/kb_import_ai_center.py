"""Імпорт старої бази AI ЦЕНТРУ в єдину базу знань.

    python manage.py kb_import_ai_center            # ПРОБНИЙ запуск: лише показує, нічого не пише
    python manage.py kb_import_ai_center --live     # записати (повторний запуск нічого не дублює)
    --all-draft   навіть 6 записів доставки 13.09 — чернетками
    --no-seeds    без 12 правил із коду CRM
"""
from django.core.management.base import BaseCommand

from apps.knowledge.importer import APPROVED_ON_13_09, apply_import, plan_import, summary
from apps.knowledge.models import KnowledgeItem

TOPIC = dict(KnowledgeItem.TOPICS)
STATUS = dict(KnowledgeItem.STATUS)


class Command(BaseCommand):
    help = "Імпорт старої бази AI ЦЕНТРУ (crm_kbentry) у єдину базу знань (за замовчуванням — пробний запуск)"

    def add_arguments(self, p):
        p.add_argument("--live", action="store_true", help="Записати в базу (без прапорця — лише звіт)")
        p.add_argument("--all-draft", action="store_true", help="Усе чернетками, навіть доставку 13.09")
        p.add_argument("--no-seeds", action="store_true", help="Не додавати правила з коду CRM")
        p.add_argument("--samples", type=int, default=2, help="Скільки прикладів показати на тему")

    def handle(self, *a, **o):
        plan = plan_import(approve_ids=[] if o["all_draft"] else APPROVED_ON_13_09, seeds=not o["no_seeds"])
        s = summary(plan)
        w = self.stdout.write
        w("=" * 70)
        w("ІМПОРТ СТАРОЇ БАЗИ AI ЦЕНТРУ → єдина база знань  [%s]" % ("ЗАПИС" if o["live"] else "ПРОБНИЙ ЗАПУСК, нічого не записано"))
        w("Уже імпортовано раніше (пропуск): %d · без питання/відповіді (пропуск): %d" % (s["skipped_existing"], s["skipped_empty"]))
        w("Буде створено: %d записів старої бази + %d правил із коду CRM" % (s["rows"], s["seeds"]))
        w("За статусом: " + ", ".join("%s %d" % (STATUS.get(k, k), v) for k, v in sorted(s["by_status"].items())))
        w("Одразу «Затверджено» (памʼятка доставки 13.09): %s" % (s["approved_ids"] or "—"))
        w("За темами: " + ", ".join("%s %d" % (TOPIC.get(k, k), v) for k, v in sorted(s["by_topic"].items(), key=lambda x: -x[1])))
        if s["flagged"]:
            total = len({i for ids in s["flagged"].values() for i in ids})
            w("⚠️ З помилками аудиту (лише чернеткою, з позначкою): %d записів" % total)
            for msg, ids in s["flagged"].items():
                w("   · %s — %d: %s%s" % (msg, len(ids), ids[:12], " …" if len(ids) > 12 else ""))
        if plan["seeds"]:
            w("Правила з коду CRM (чернетки на затвердження): " + "; ".join(r["title"] for r in plan["seeds"]))
        if o["samples"] > 0:
            w("-" * 70)
            shown = {}
            for r in plan["rows"]:
                if shown.get(r["topic"], 0) >= o["samples"]:
                    continue
                shown[r["topic"]] = shown.get(r["topic"], 0) + 1
                w("[%s · %s] №%s %s" % (TOPIC.get(r["topic"], r["topic"]), STATUS[r["status"]], r["kb_id"], r["title"][:90]))
        w("=" * 70)
        if not o["live"]:
            w("Щоб записати: python manage.py kb_import_ai_center --live")
            return
        n = apply_import(plan)
        w("ЗАПИСАНО: %d записів. Повторний запуск нічого не дублює." % n)
