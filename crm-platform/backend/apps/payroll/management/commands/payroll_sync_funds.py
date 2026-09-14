"""payroll_sync_funds [--dry] — звʼязані фонди Фінмоделі := сума «За ставками» (fm-link, 14.09.2026).

Чіпає ЛИШЕ фонди зі списку «Автоматично зі Ставок» (PayPolicy.params["linked_funds"]; за замовчуванням порожній).
Пише лише те, що змінилось, з історією у «Ставках» (PayRateLog fund_sync, «авто зі Ставок»).
--dry — лише показати було → стало, нічого не записувати.
Cron (НЕ встановлено; додати вручну після «ок» Олега):
50 4 * * * /usr/bin/flock -n /tmp/payroll_funds.lock -c 'cd /root/gmideas/crm-platform && /usr/bin/docker compose -f docker-compose.prod.yml exec -T web nice -n 15 python manage.py payroll_sync_funds' >> /var/log/payroll_funds.log 2>&1
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payroll.fund_link import _fmt, linked_ids, sync_linked


class Command(BaseCommand):
    help = "Звʼязані фонди Фінмоделі := сума за Ставками співробітників (лише звʼязані; --dry — лише показати)"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true", help="нічого не записувати, лише показати було → стало")

    def handle(self, *args, **opts):
        dry = bool(opts.get("dry"))
        stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        ids = linked_ids()
        if not ids:
            self.stdout.write(f"{stamp} Звʼязаних фондів немає — нічого не робимо.")
            return
        res = sync_linked(dry=dry)
        head = "DRY (нічого не записано)" if dry else "ЗАПИСАНО"
        if not res:
            self.stdout.write(f"{stamp} Звʼязані фонди {ids}: усе вже збігається зі ставками.")
            return
        self.stdout.write(f"{stamp} {head}:")
        for r in res:
            self.stdout.write(f"  фонд #{r['fund_id']} «{r['name']}»: {_fmt(r['before'], r['unit'])} → {_fmt(r['after'], r['unit'])}")
