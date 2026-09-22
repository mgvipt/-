"""Щоденний рецензент закритих чатів (команда агентів, фаза 1). ЗА ЗАМОВЧУВАННЯМ ВИМКНЕНИЙ.

    python manage.py kb_review_daily --dry                  # без ШІ і без запису: які чати, що знайшла перевірка кодом, скільки коштувало б
    python manage.py kb_review_daily                        # ШІ НЕ викликає (14.09): лише кнопка «Запустити перевірку» в AI ЦЕНТРІ
    --date 2026-09-13   день (за замовчуванням — вчора)
    --sample 20         скільки чатів
    --conversation ID   один конкретний чат (для перевірки на тестовому діалозі)

Пише тільки ЧЕРНЕТКИ в базу знань (з посиланням на діалог). Затверджене не змінює, клієнтам не пише.
"""
from datetime import date

from django.core.management.base import BaseCommand

from apps.knowledge.models import KnowledgeSettings
from apps.knowledge.reviewer import run


class Command(BaseCommand):
    help = "Рецензент закритих чатів → чернетки в базу знань (вимкнено за замовчуванням)"

    def add_arguments(self, p):
        p.add_argument("--dry", action="store_true", help="Без ШІ і без запису — лише звіт")
        p.add_argument("--date", default="")
        p.add_argument("--sample", type=int, default=0)
        p.add_argument("--conversation", type=int, default=0)
        p.add_argument("--ai-only", action="store_true", dest="ai_only",
                       help="Перевіряти діалоги, де відповідав наш ШІ-продавець (а не лише закриті чати)")

    def handle(self, *a, **o):
        cfg = KnowledgeSettings.get()
        dry = o["dry"]
        if not dry:
            # 14.09 (ai-kb2, рішення Олега): контролер працює ЛИШЕ за запуском з інтерфейсу — AI ЦЕНТР → База знань ✓ →
            # «Контролер» → «Запустити перевірку». Розкладу немає: навіть якщо цю команду додадуть у cron, ШІ не викликається.
            self.stdout.write("Автозапуск контролера ВИМКНЕНИЙ: перевірка з ШІ — лише кнопкою «Запустити перевірку» в AI ЦЕНТРІ "
                              "(База знань ✓ → Контролер). Нічого не зроблено, $0. Безкоштовна перевірка кодом: --dry")
            return
        day = date.fromisoformat(o["date"]) if o["date"] else None
        r = run(day=day, sample=o["sample"] or None, dry=dry, conversation_id=o["conversation"] or None,
                ai_only=o.get("ai_only", False))
        w = self.stdout.write
        w("РЕЦЕНЗЕНТ %s [%s] модель %s" % (r["day"], "ПРОБНИЙ ЗАПУСК — без ШІ, нічого не записано" if dry else "ЗАПИС", r["model"]))
        w("Закритих чатів у вибірці: %d %s" % (len(r["picked"]), r["picked"][:30]))
        w("Перевірка кодом (безкоштовно): %d знахідок" % len(r["lint"]))
        for f in r["lint"][:30]:
            w("  · діалог №%s — %s (%s): «%s»" % (f["conversation_id"], f["problem"], f["who"], f["quote"][:90]))
        if dry:
            w("Якби був увімкнений: %d викликів Claude ≈ $%s за цей день" % (len(r["picked"]), r["est_cost_usd"]))
            return
        w("Claude: %d викликів, %d знахідок, створено чернеток: %d" % (r["ai_calls"], r["ai_findings"], r["items_created"]))
        for e in r["errors"]:
            w("  ! " + e)
