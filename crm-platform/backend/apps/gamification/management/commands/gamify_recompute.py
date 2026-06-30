import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.crm.models import DialogAnalysis, Deal
from apps.gamification.xp import award_for_analysis, award, give_badge, recompute_level
from apps.gamification.views import sales_managers


class Command(BaseCommand):
    help = "Перерахувати XP/рівні: якість (усі розбори) + недавні won-угоди. Ідемпотентно."

    def handle(self, *a, **o):
        nq = 0
        for da in DialogAnalysis.objects.exclude(manager__isnull=True).iterator():
            award_for_analysis(da); nq += 1
        mids = list(sales_managers().values_list("id", flat=True))
        recent = timezone.now() - datetime.timedelta(days=45)
        nd = 0
        for d in (Deal.objects.filter(stage__is_won=True, owner_id__in=mids)
                  .filter(closed_at__gte=recent).select_related("owner")):
            r = award(d.owner, "deal_won", 60, "deal", d.id, {"amount": str(d.amount or 0)})
            try:
                amt = float(d.amount or 0)
                if amt:
                    award(d.owner, "deal_check", min(80, round(amt / 1000)), "dealcheck", d.id)
            except Exception:
                pass
            if r:
                give_badge(d.owner, "first_blood")
                nd += 1
        for mid in mids:
            recompute_level(mid)
        self.stdout.write(f"gamify: quality={nq} won={nd}")
