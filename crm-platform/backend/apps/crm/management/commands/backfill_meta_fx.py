"""Дозаповнення гривневого еквіваленту реклами (spend_uah) за ОФІЦІЙНИМ курсом НБУ.

Навіщо: колонки spend_uah/fx_rate_to_uah додані міграцією пізніше за старт синку,
а watch-синк переписує лише останні дні → історія лишилась без гривні, і на екрані
«Реклама по курсу НБУ», «Прибуток після реклами», «ROAS», «ROMI» показували «—».

БЕЗПЕЧНО: заповнює ТІЛЬКИ порожні (spend_uah IS NULL). Нічого не перезаписує.
Ідемпотентно. Без --apply — лише DRY-RUN.
"""
from django.core.management.base import BaseCommand
from apps.crm.models import MetaAdDailyStat
from apps.crm.meta_marketing import _nbu_rate


class Command(BaseCommand):
    help = "Дозаповнити spend_uah/fx_rate_to_uah за курсом НБУ (тільки порожні)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="реально записати")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        qs = MetaAdDailyStat.objects.filter(spend__gt=0, spend_uah__isnull=True)
        pairs = sorted({(r["currency"] or "USD", r["date"]) for r in qs.values("currency", "date")})
        self.stdout.write("Рядків без гривні: %s | унікальних дат-валют: %s" % (qs.count(), len(pairs)))
        rates = {}
        no_rate = []
        for cur, day in pairs:
            rate = _nbu_rate(cur, day)
            if rate:
                rates[(cur, day)] = rate
            else:
                no_rate.append((cur, day))
        self.stdout.write("Курс отримано на %s дат | не вдалось: %s" % (len(rates), len(no_rate)))
        if no_rate:
            self.stdout.write("  без курсу: %s" % ", ".join("%s %s" % (c, d) for c, d in no_rate[:10]))
        done = 0
        total_uah = 0
        for (cur, day), rate in rates.items():
            rows = qs.filter(currency=cur, date=day)
            for r in rows:
                uah = (r.spend or 0) * rate
                total_uah += float(uah)
                done += 1
                if apply:
                    r.spend_uah = uah
                    r.fx_rate_to_uah = rate
                    r.save(update_fields=["spend_uah", "fx_rate_to_uah"])
        mode = "APPLIED" if apply else "DRY-RUN"
        self.stdout.write("[%s] заповнено рядків: %s | сума реклами у грн: %s" % (mode, done, round(total_uah, 2)))
