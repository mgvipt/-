"""Місця і вага відвантажень з Нової Пошти → статистика складу (19.09.2026).

    python manage.py wh_np_sync            # відвантаження за 3 дні (крон щогодини)
    python manage.py wh_np_sync --days 31  # за місяць (разово)
    python manage.py wh_np_sync --dry      # лише показати

Лише ЧИТАННЯ НП; пише тільки job.done_snapshot["np"]. Оплату не змінює.
"""
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.warehouse.models import WarehouseJob
from apps.warehouse.np_places import fetch_np, pack_diff, per_seat, sync_job, tiers_for


class Command(BaseCommand):
    help = "Місця і вага відвантажень з Нової Пошти (статистика складу)"

    def add_arguments(self, p):
        p.add_argument("--days", type=int, default=3)
        p.add_argument("--dry", action="store_true")

    def handle(self, *a, **o):
        since = timezone.now() - timedelta(days=o["days"])
        jobs = (WarehouseJob.objects.filter(status="shipped", shipped_at__gte=since)
                .exclude(deal__ttn="").exclude(deal__ttn__isnull=True).select_related("deal", "deal__contact"))
        ok = miss = 0
        for job in jobs:
            try:
                if o["dry"]:
                    np = fetch_np(job.deal)
                    if np:
                        w, src = per_seat(np, (job.deal.np_data or {}).get("seats"))
                        np.update({"per_seat": w, "per_seat_src": src, "tiers": tiers_for(w)})
                else:
                    np = sync_job(job)
            except Exception as e:  # мережа / НП — наступного разу
                self.stdout.write("  #%s помилка НП: %s" % (job.id, str(e)[:80]))
                np = None
            if not np:
                miss += 1
                continue
            ok += 1
            if o["dry"]:
                self.stdout.write("  #%s сделка %s: НП %s місць, %s кг (%s); CRM %s/%s/%s" % (
                    job.id, job.deal_id, np["seats"], np["weight"], np["per_seat_src"],
                    job.pack_le5_count, job.pack_le10_count, job.pack_le20_count))
            time.sleep(0.2)
        self.stdout.write("Готово: з НП %d, без даних НП %d" % (ok, miss))
        if not o["dry"]:
            diff = [pack_diff(j) for j in jobs]
            diff = [d for d in diff if d]
            if diff:
                self.stdout.write("Упаковка за місцями НП проти нарахованого: %s ₴" % sum(d["diff"] for d in diff))
