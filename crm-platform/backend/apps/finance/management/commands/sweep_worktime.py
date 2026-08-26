"""Антипростій + авто-завершення забутих змін. Запускається кроном кожні 3 хв.

Логіка:
1. Авто-пауза за простій — для відділів з idle_timeout_min > 0 (офіс/продажі).
   Якщо зміна активна, НЕ на паузі, і немає «пульсу» (last_seen_at) довше порогу
   → ставимо авто-паузу (reason=idle). Час простою не рахується робочим.
   Склад/Тонування (idle_timeout_min = 0) — НЕ чіпаємо (працюють руками, відходять від ПК).
2. Авто-завершення забутої зміни — для ВСІХ: якщо співробітник пішов і не натиснув
   «Завершити» (немає пульсу дуже довго АБО зміна відкрита з попереднього дня)
   → закриваємо зміну на момент останньої присутності, щоб не роздувати години.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

# Скільки хвилин без пульсу вважати «пішов і забув завершити» (авто-стоп). Оле́г може міняти.
AUTO_CLOSE_MIN = 240  # 4 години


class Command(BaseCommand):
    help = "Антипростій: авто-пауза за простій + авто-завершення забутих змін"

    def handle(self, *args, **opts):
        from apps.finance.models import WorkSession
        try:
            from apps.crm.models import log_activity
        except Exception:
            log_activity = lambda *a, **k: None

        now = timezone.now()
        paused_n = closed_n = 0
        active = WorkSession.objects.filter(ended_at__isnull=True).select_related("user", "user__department")
        for ws in active:
            has_hb = ws.last_seen_at is not None   # чи шле фронт heartbeat (нова версія)
            last = ws.last_seen_at or ws.started_at
            gap_min = (now - last).total_seconds() / 60
            try:
                idle_to = int(ws.user.effective_idle_timeout())  # особистий поріг або відділу
            except Exception:
                idle_to = 15
            name = ws.user.get_full_name() or ws.user.username

            # 1) авто-завершення забутої зміни: давно без пульсу (лише коли є heartbeat) АБО зміна з минулого дня
            stale = has_hb and gap_min >= AUTO_CLOSE_MIN
            overnight = ws.started_at.date() < now.date() and gap_min >= 60
            if stale or overnight:
                if ws.paused_at:
                    ws.paused_seconds += int((now - ws.paused_at).total_seconds())
                    ws.paused_at = None
                    for p in reversed(ws.pauses or []):
                        if not p.get("end"):
                            p["end"] = last.isoformat(); break
                ws.ended_at = last  # закриваємо на момент останньої реальної присутності
                ws.save()
                log_activity("contact", 0, "Авто-завершення дня",
                             "%s не завершив зміну — авто-стоп на %s" % (name, timezone.localtime(last).strftime("%H:%M")),
                             ws.user, "Система")
                closed_n += 1
                continue

            # 2) авто-пауза за простій (лише офіс/продажі з idle_timeout_min > 0; тільки за наявності heartbeat)
            if has_hb and idle_to > 0 and not ws.paused_at and gap_min >= idle_to:
                ws.paused_at = now
                plist = ws.pauses or []
                plist.append({"start": now.isoformat(), "end": None, "reason": "idle"})
                ws.pauses = plist
                ws.save()
                log_activity("contact", 0, "Авто-пауза (простій)",
                             "%s — немає активності %d хв, авто-пауза" % (name, int(gap_min)),
                             ws.user, "Система")
                paused_n += 1

        # Звести стан Юлі з ФАКТИЧНИМИ змінами: авто-пауза/авто-закриття вище могли
        # змінити к-сть активних sales-менеджерів ПОВЗ hook у WorkTimeView → тихий режим
        # Юлі дрейфував. apply_yulia_shift_toggle() чіпає ChatPlace ЛИШЕ коли треба
        # (want != збережений стан) — при стабільному стані 0 зайвих запитів.
        try:
            from apps.inbox.yulia_toggle import apply_yulia_shift_toggle
            apply_yulia_shift_toggle()
        except Exception:
            pass
        self.stdout.write("sweep_worktime: авто-пауз %d, авто-завершень %d (активних змін %d)" % (paused_n, closed_n, active.count()))
