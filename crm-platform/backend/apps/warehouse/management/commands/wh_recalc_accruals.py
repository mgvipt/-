"""Перерахунок нарахувань складу за відвантаження за регламентом ваги/упаковки v2 (15.09.2026).

  python manage.py wh_recalc_accruals --from 2026-09-14 --to 2026-09-15            # DRY: лише показати було → стане
  python manage.py wh_recalc_accruals --from 2026-09-14 --to 2026-09-15 --live     # записати
  --jobs 471,527                                                                   # лише ці задачі (для кроку «1–2»)

Чіпає ЛИШЕ записи ЗП цих відвантажень з типами «Вага відвантаження», «Упаковка», «Тонування», «Збірка тестового
набору». Людина і дата запису — як були. Ставки — ті, що діяли на дату запису: вага, тонування і тест-набір — ставка
зі старого запису (якщо був), упаковка до 15.09.2026 — 8 / 13 / 20 ₴ (бекап /root/wh_pack_rates_backup_20260915.json),
з 15.09 — з Фінмоделі. Затверджені відомості ЗП не змінюються. Перед записом друкує BACKUP-рядок з видаленими записами."""
import datetime
import json
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

OPS = ("shipment_weight", "packing", "tinting", "test_set")
PACK_SWITCH = datetime.date(2026, 9, 15)
PACK_BEFORE = {"T5": Decimal("8"), "T10": Decimal("13"), "T20": Decimal("20")}


def _q(x):
    return Decimal(x).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = "Перерахувати ЗП складу за відвантаження за регламентом v2 (DRY за замовчуванням)"

    def add_arguments(self, p):
        p.add_argument("--from", dest="d1", required=True)
        p.add_argument("--to", dest="d2", required=True)
        p.add_argument("--jobs", default="")
        p.add_argument("--live", action="store_true")

    def handle(self, d1, d2, jobs, live, **kw):
        from apps.payroll.models import PayrollRun
        from apps.warehouse import wh_views
        from apps.warehouse.models import WarehouseJob, WarehousePayrollEntry as W
        d1 = datetime.date.fromisoformat(d1)
        d2 = datetime.date.fromisoformat(d2)
        qs = (WarehouseJob.objects.filter(status="shipped", shipped_at__isnull=False)
              .select_related("deal", "deal__funnel").order_by("shipped_at", "id"))
        ids = [int(x) for x in jobs.split(",") if x.strip().isdigit()]
        if ids:
            qs = qs.filter(id__in=ids)
        tot_old = tot_new = Decimal("0")
        changed = 0
        for job in qs:
            day = timezone.localtime(job.shipped_at).date()
            if not (d1 <= day <= d2):
                continue
            old = list(W.objects.filter(job=job, op_type__in=OPS).order_by("id"))
            emp = old[0].employee if old else job.assignee
            if emp is None:
                self.stdout.write(f"job {job.id}: немає людини — пропуск")
                continue
            wd = old[0].work_date if old else day
            if PayrollRun.objects.filter(user=emp, period=wd.strftime("%Y-%m"), status="approved").exists():
                self.stdout.write(f"job {job.id} #{job.deal_id}: відомість {wd:%Y-%m} затверджена — не чіпаю")
                continue
            snap_w = Decimal(str((job.done_snapshot or {}).get("weight") or 0))
            pay_packing = not (snap_w > 0 and job.packed and not any(e.op_type == "packing" for e in old))
            rows, meta = wh_views._accrual_plan(job, pay_packing)
            old_rate = {e.op_type: e.rate_applied for e in old if e.op_type != "packing"}
            new = []
            for op, amt, fields in rows:
                f = dict(fields)
                if op == "packing":
                    if wd < PACK_SWITCH:
                        r = PACK_BEFORE[f["pack_tier"]]
                        cnt = int(round(float(amt / f["rate_applied"]))) if f["rate_applied"] else 0
                        f["rate_applied"] = r
                        amt = r * cnt
                elif op in old_rate and op in ("shipment_weight", "test_set"):
                    r = old_rate[op]
                    base = f.get("quantity_kg") if op == "shipment_weight" else (amt / f["rate_applied"] if f["rate_applied"] else 0)
                    f["rate_applied"] = r
                    amt = Decimal(base or 0) * r
                elif op == "tinting" and op in old_rate:
                    f["rate_applied"] = old_rate[op]
                    amt = Decimal(f.get("base_value") or 0) * old_rate[op]
                new.append((op, _q(amt), f))
            o_sum = sum((e.amount for e in old), Decimal("0"))
            n_sum = sum((a for _op, a, _f in new), Decimal("0"))
            tot_old += o_sum
            tot_new += n_sum
            o_desc = ", ".join(f"{e.op_type}={e.amount}" for e in old) or "—"
            n_desc = ", ".join(f"{op}={a}" for op, a, _f in new) or "—"
            self.stdout.write(f"job {job.id} #{job.deal_id} {wd:%d.%m} {emp.username}: {o_sum} → {n_sum} ₴ "
                              f"| кг {job.shipped_weight_kg} → {meta['weight']} | місця {meta['tiers']}\n"
                              f"    було: {o_desc}\n    стане: {n_desc}")
            for h in meta.get("how", []):
                self.stdout.write(f"      · {h}")
            if o_sum == n_sum and len(old) == len(new):
                continue
            changed += 1
            if not live:
                continue
            with transaction.atomic():
                backup = [{"id": e.id, "employee": e.employee_id, "work_date": e.work_date.isoformat(), "job": e.job_id,
                           "deal": e.deal_id, "op_type": e.op_type, "quantity_kg": str(e.quantity_kg or ""),
                           "pack_tier": e.pack_tier, "base_value": str(e.base_value or ""),
                           "rate_applied": str(e.rate_applied), "amount": str(e.amount), "note": e.note} for e in old]
                self.stdout.write("BACKUP " + json.dumps(backup, ensure_ascii=False))
                W.objects.filter(id__in=[e.id for e in old]).delete()
                for op, amt, f in new:
                    W.objects.create(employee=emp, work_date=wd, job=job, deal=job.deal, op_type=op, amount=amt,
                                     source="recalc", **f)
                tiers = meta["tiers"]
                job.shipped_weight_kg = meta["weight"]
                job.pack_le5_count, job.pack_le10_count, job.pack_le20_count = tiers["T5"], tiers["T10"], tiers["T20"]
                snap = dict(job.done_snapshot or {})
                snap.update({"weight": str(meta["weight"]), "tiers": tiers, "rule": "v2", "how": meta.get("how", [])[:40],
                             "weightless": [w.get("product_id") for w in meta.get("weightless", [])],
                             "recalc_at": timezone.now().isoformat()})
                job.done_snapshot = snap
                job.save(update_fields=["shipped_weight_kg", "pack_le5_count", "pack_le10_count", "pack_le20_count",
                                        "done_snapshot"])
        mode = "ЗАПИСАНО" if live else "DRY (нічого не записано)"
        self.stdout.write(f"{mode}: змінюється відвантажень {changed}; разом було {tot_old} ₴ → стане {tot_new} ₴")
