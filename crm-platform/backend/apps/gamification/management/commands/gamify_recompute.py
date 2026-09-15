"""Щогодинний крон «Розвитку» (17 * * * *). Розвиток v2 (16.09.2026): бали лише за НОВИМИ правилами (rules.py) —
тест-набір → основне, основне без знижки, відгук, розбір дзвінка. Балів за сам факт виграної угоди більше НЕ дає.
Ідемпотентно (повторний запуск нічого не дублює); лише додає бали за останні --days днів; старих балів не чіпає
(їх архівує окрема команда gamify_rules_v2 --live — за рішенням власника).

    python manage.py gamify_recompute            # як у кроні: записати нові бали за 45 днів
    python manage.py gamify_recompute --dry      # лише показати, що було б записано
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.gamification import rules
from apps.gamification.xp import award_for_analysis, recompute_level


class Command(BaseCommand):
    help = "Бали розвитку за новими правилами (Розвиток v2): останні N днів, ідемпотентно; без балів за виграну угоду."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=45)
        parser.add_argument("--dry", action="store_true", help="нічого не записувати")

    def handle(self, *a, **o):
        today = timezone.localdate()
        since = today - timedelta(days=max(1, o["days"]))
        live = not o["dry"]
        res = rules.apply(rules.collect(since, today), live=live)
        pending = rules.quality_pending(since, today)
        if live:
            for da in pending:
                award_for_analysis(da)
            for mid in {e["manager_id"] for e in res["new"]} | {da.manager_id for da in pending}:
                recompute_level(mid)
        by = rules.summarize(res["new"])
        parts = [f"{mid}:" + ",".join(f"{k}={v[0]}/{v[1]}xp" for k, v in kinds.items()) for mid, kinds in by.items()]
        self.stdout.write(f"gamify v2 {'LIVE' if live else 'DRY'} {since}..{today}: нових={len(res['new'])} "
                          f"вже були={res['skipped']} розборів без балів={len(pending)} " + " ".join(parts))
