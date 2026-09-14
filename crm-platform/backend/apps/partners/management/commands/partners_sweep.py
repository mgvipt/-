"""Нічна перевірка рівнів партнерів. За замовчуванням — ЛИШЕ ПОКАЗУЄ (DRY-RUN), нічого не пише.

  python manage.py partners_sweep            # хто б підвищився + кандидати (не партнери з великим оборотом)
  python manage.py partners_sweep --apply    # підвищити (понижень немає ніколи), оновити кеш обороту

Cron (Netcup, після «ок» Олега): 20 5 * * * … docker compose -f docker-compose.prod.yml exec -T web
    nice -n 15 python manage.py partners_sweep --apply
"""
from django.core.management.base import BaseCommand

from apps.crm.models import Contact
from apps.partners.models import PartnerLevel, PartnerSettings, PartnerStatus
from apps.partners.services import level_for, q2, recompute, turnover_map


class Command(BaseCommand):
    help = "Партнери: перерахунок обороту і автопідвищення рівня (DRY-RUN за замовчуванням)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записати зміни (інакше лише показати)")
        parser.add_argument("--candidates", type=int, default=20, help="Скільки кандидатів показати")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        st = PartnerSettings.get()
        levels = list(PartnerLevel.objects.filter(is_active=True).order_by("order"))
        mode = "LIVE" if apply else "DRY-RUN (нічого не пишу)"
        self.stdout.write("Партнери: %s; оборот з %s; автопідвищення %s" % (
            mode, st.turnover_from, "увімкнено" if st.auto_raise else "ВИМКНЕНО"))
        statuses = list(PartnerStatus.objects.select_related("level", "contact").order_by("id"))
        raised = 0
        for s in statuses:
            res = recompute(s.contact_id, apply=apply, st=st, levels=levels)
            if res is None:
                continue
            mark = "↑ %s → %s" % (res["old"].name, res["new"].name) if res["changed"] else "без змін (%s)" % res["old"].name
            if not s.is_active:
                mark += " · галочку знято"
            self.stdout.write("  контакт #%s: оборот %s ₴ — %s" % (s.contact_id, q2(res["turnover"]), mark))
            raised += 1 if res["changed"] else 0
        self.stdout.write("Партнерів: %s; %s: %s" % (len(statuses), "підвищено" if apply else "підвищилось би", raised))

        first_paid = [lv for lv in levels if lv.threshold_uah > 0]
        if first_paid:
            border = min(lv.threshold_uah for lv in first_paid)
            partner_ids = {s.contact_id for s in statuses}
            rows = sorted(((cid, t) for cid, t in turnover_map(None, st).items()
                           if cid not in partner_ids and t >= border), key=lambda x: -x[1])
            self.stdout.write("Кандидати (не партнери, оборот ≥ %s ₴): %s" % (q2(border), len(rows)))
            for cid, t in rows[:opts["candidates"]]:
                self.stdout.write("  контакт #%s: %s ₴ → рівень за оборотом «%s»" % (cid, q2(t), level_for(t, levels).name))
        if not apply:
            self.stdout.write("DRY-RUN: нічого не записано. Для запису: --apply")
