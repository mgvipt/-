"""Тижнева ВИПАДКОВА вибірка чатів для ШІ-розбору (Розвиток v2, 16.09.2026). ВИМКНЕНО за замовчуванням.

Навіщо: «Якість дзвінків» зараз рахується лише з дзвінків; чати ШІ сам не розбирає (analyst_auto вимкнено), а
розбори «вручну» людина може вибирати (лише вдалі). Випадкова вибірка — чесно: N чатів кожного менеджера за тиждень,
де він сам писав клієнту. Розбір зараховується тому, хто писав (автор повідомлень).

Коштує грошей: ≈ $0,02 за розбір (факт CRM: 338 розборів за 60 днів = $5,54). 3 чати × 3 менеджери × 4,3 тижня ≈ $0,8/міс.

    python manage.py sample_chats_weekly          # DRY: які чати були б розібрані і скільки коштуватиме
    python manage.py sample_chats_weekly --live   # розібрати (лише якщо власник увімкнув у «Розвиток → Налаштування»)
Крон (додати лише коли власник увімкне): 30 9 * * 1 … python manage.py sample_chats_weekly --live
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.gamification.models import GamSettings
from apps.gamification.views import sales_managers

COST_PER_ANALYSIS_USD = 0.02
MIN_OUT, MIN_IN = 3, 3


def pick(manager, since, until, n, seed):
    from apps.crm.models import DialogAnalysis
    from apps.inbox.models import Message
    rows = (Message.objects.filter(direction="out", internal=False, sender=manager, created_at__gte=since, created_at__lt=until)
            .values("conversation_id").annotate(n=Count("id")).filter(n__gte=MIN_OUT))
    cands = sorted(r["conversation_id"] for r in rows)
    recent = set(DialogAnalysis.objects.filter(conversation_id__in=cands, created_at__gte=until - timedelta(days=30))
                 .values_list("conversation_id", flat=True))
    ok = [c for c in cands if c not in recent and
          Message.objects.filter(conversation_id=c, direction="in", created_at__gte=since, created_at__lt=until).count() >= MIN_IN]
    rnd = random.Random(seed)
    return rnd.sample(ok, min(n, len(ok)))


class Command(BaseCommand):
    help = "Випадкова тижнева вибірка чатів для ШІ-розбору (лише якщо увімкнено власником). DRY за замовчуванням."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *a, **o):
        s = GamSettings.get()
        w = self.stdout.write
        if not s.chat_sampling:
            w("Вибірку чатів ВИМКНЕНО («Розвиток» → налаштування власника). Нічого не роблю — ШІ не викликається.")
            return
        until = timezone.now()
        since = until - timedelta(days=max(1, o["days"]))
        wk = timezone.localdate().isocalendar()
        total = 0
        plan = []
        for m in sales_managers().order_by("id"):
            ids = pick(m, since, until, s.chat_sample_per_week, f"{m.id}-{wk[0]}-{wk[1]}")
            plan.append((m, ids))
            total += len(ids)
            w(f"{m.get_full_name() or m.username}: чатів у вибірці {len(ids)} {ids}")
        w(f"Разом розборів: {total} ≈ ${total * COST_PER_ANALYSIS_USD:.2f}")
        if not o["live"]:
            w("DRY: ШІ не викликався. Додайте --live, щоб розібрати.")
            return
        from apps.crm.models import DialogAnalysis, Deal
        from apps.crm.sales_analyst import analyze_dialog
        from apps.inbox.models import Conversation
        done = 0
        for m, ids in plan:
            for cid in ids:
                conv = Conversation.objects.filter(pk=cid).first()
                if not conv:
                    continue
                msgs = list(conv.messages.order_by("id").values("direction", "text"))[-40:]
                r = analyze_dialog(msgs, context="Випадкова вибірка чатів тижня (Розвиток)", kind="чат")
                if not isinstance(r, dict) or r.get("empty") or r.get("error"):
                    continue
                deal = None
                if conv.contact_id:
                    deal = (Deal.objects.filter(contact_id=conv.contact_id, owner=m).order_by("-id").first()
                            or Deal.objects.filter(contact_id=conv.contact_id).order_by("-id").first())
                da = DialogAnalysis(conversation=conv, deal=deal, manager=m, kind="chat",
                                    overall_score=r.get("overall", 0) or 0, scores=r.get("scores", {}) or {},
                                    strengths=r.get("strengths", ""), why_not_selling=r.get("why_not_selling", ""),
                                    recommended_reply=r.get("recommended_reply", ""), coaching=r.get("coaching", ""))
                da._rzv_credit = "sample"
                da.save()
                done += 1
        w(f"LIVE: розібрано {done} чатів.")
