# -*- coding: utf-8 -*-
"""Перерахунок економіки угод. ТРИ КРОКИ (правило масових операцій):

  1) DRY (за замовчуванням) — нічого не пише; сесія бази в режимі «лише читання»:
       python manage.py recompute_deal_economics --from 2026-07-01 --to 2026-08-31 --fetch-np
  2) 2 угоди:   ... --live --limit 2
  3) усі:       ... --live            (+ --lock — закрити місяць: авто-перерахунок рядки не змінює)

--fetch-np    — лише ЧИТАННЯ НП API (getStatusDocuments пачками по 100) для ТТН без np_cost;
                у LIVE платник/вартість додаються в np_data["np_cost"] (ОДНИМ ключем, інші не чіпаємо).
--all-deals   — усі угоди періоду (за замовчуванням — лише ті, де є оплачений платіж).
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.dealecon import services as S

CRM_URL = "https://crm.wallcovdec.com.ua/deals/%s"


def _n(x):
    return ("{:,.0f}".format(float(x or 0))).replace(",", " ")


def _est_part(res):
    """Скільки з вирахуваного — оцінкою (для прозорості DRY)."""
    tot = Decimal("0")
    for k in S.COST_KEYS:
        s = (res["sources"] or {}).get(k) or {}
        amt = Decimal(str(res[k]))
        if s.get("kind") == "estimate":
            tot += amt
        elif s.get("kind") == "mixed":
            parts = s.get("parts") or {}
            if k == "commission":
                tot += sum((Decimal(str(v.get("used") or 0)) for v in parts.values()
                            if isinstance(v, dict) and v.get("kind") == "estimate"), Decimal("0"))
            elif k == "packaging":
                tot += Decimal(str(parts.get("material") or 0))
    return tot


class Command(BaseCommand):
    help = "Економіка угод: DRY за замовчуванням; --limit N; --live; --fetch-np; --lock"

    def add_arguments(self, p):
        p.add_argument("--from", dest="date_from", default="", help="дата створення угоди від (РРРР-ММ-ДД)")
        p.add_argument("--to", dest="date_to", default="", help="дата створення угоди до (включно)")
        p.add_argument("--deal", default="", help="id угод через кому")
        p.add_argument("--funnel", default="", help="id воронок через кому")
        p.add_argument("--all-deals", action="store_true", help="усі угоди, не лише з оплатою")
        p.add_argument("--limit", type=int, default=0)
        p.add_argument("--live", action="store_true", help="ЗАПИСАТИ рядки економіки")
        p.add_argument("--lock", action="store_true", help="разом з --live: закрити рядки (закритий місяць)")
        p.add_argument("--fetch-np", action="store_true", help="дочитати платника/вартість з НП API (лише читання)")
        p.add_argument("--show", type=int, default=0, help="показати N угод детально")

    def handle(self, *args, **o):
        if o["lock"] and not o["live"]:
            raise CommandError("--lock працює лише разом з --live")
        guard = False
        if not o["live"] and connection.vendor == "postgresql" and not connection.in_atomic_block:
            with connection.cursor() as c:
                c.execute("SET default_transaction_read_only = on")   # DRY фізично не може писати
            guard = True
        try:
            self._go(o)
        finally:
            if guard:
                with connection.cursor() as c:
                    c.execute("SET default_transaction_read_only = off")

    def _go(self, o):
        from apps.crm.models import Deal
        from apps.dealecon.models import DealEconomics
        live = o["live"]
        ids = [int(x) for x in str(o["deal"] or "").replace(" ", "").split(",") if x]
        funnels = [int(x) for x in str(o["funnel"] or "").replace(" ", "").split(",") if x]
        qs = Deal.objects.all()
        if ids:
            qs = qs.filter(pk__in=ids)
        if o["date_from"]:
            qs = qs.filter(created_at__date__gte=o["date_from"])
        if o["date_to"]:
            qs = qs.filter(created_at__date__lte=o["date_to"])
        if funnels:
            qs = qs.filter(funnel_id__in=funnels)
        if not o["all_deals"] and not ids:
            qs = qs.filter(payments__is_paid=True).distinct()
        qs = qs.order_by("id").select_related("funnel").prefetch_related("items__product", "payments")
        deals = list(qs[:o["limit"]] if o["limit"] else qs)
        mode = "LIVE" if live else "DRY"
        self.stdout.write("%s: угод %d (%s…%s%s)" % (mode, len(deals), o["date_from"] or "—", o["date_to"] or "—",
                                                     ", ліміт %d" % o["limit"] if o["limit"] else ""))
        if not S.tables_ready():
            self.stdout.write("  таблиці dealecon ще немає (міграція не застосована) — норми за замовчуванням")
            if live:
                raise CommandError("LIVE неможливий без міграції dealecon")

        np_hint = {}
        if o["fetch_np"]:
            need = [d.ttn for d in deals if (d.ttn or "").strip()
                    and not (isinstance(d.np_data, dict) and isinstance(d.np_data.get("np_cost"), dict))]
            rows = S.fetch_np_rows(need)
            self.stdout.write("  НП (лише читання): запитано %d ТТН, відповідь по %d" % (len(set(need)), len(rows)))
            if live:
                stored = 0
                for d in deals:
                    r = rows.get((d.ttn or "").strip())
                    if r and S.store_np_cost(d, r, schedule=False):
                        stored += 1
                self.stdout.write("  np_data.np_cost додано в %d угод (інші ключі np_data не змінювались)" % stored)
            else:
                np_hint = {t: S.np_cost_from_row(r) for t, r in rows.items() if S.np_cost_from_row(r)}

        ctx = S.build_ctx()
        agg = defaultdict(lambda: defaultdict(Decimal))
        cheap_sender, flagged, shown = [], [], 0
        saved = locked_skip = 0
        for d in deals:
            if live:
                res = S.recompute(d, save=True, ctx=ctx, np_hint=np_hint or None)
                if res.get("locked"):
                    locked_skip += 1
                else:
                    saved += 1
                    if o["lock"]:
                        DealEconomics.objects.filter(deal_id=d.pk).update(locked=True)
            else:
                res = S.compute(d, ctx=ctx, np_hint=np_hint or None)
            card = S.card_margin(d)
            fname = d.funnel.name if d.funnel_id else "—"
            for key in ("", fname):
                a = agg[key]
                a["n"] += 1
                a["card"] += card
                a["est"] += _est_part(res)
                for k in S.NUM_FIELDS:
                    a[k] += Decimal(str(res[k]))
            dl = (res["sources"].get("delivery") or {})
            if res["delivery"] > 0 and Decimal(str(d.amount or 0)) < Decimal("6000"):
                cheap_sender.append((d.pk, d.amount, res["delivery"], dl.get("uk", "")))
            for f in res.get("flags") or []:
                flagged.append((d.pk, f.get("uk", "")))
            if shown < o["show"]:
                shown += 1
                self.stdout.write("  #%s %s: картка %s → нова %s (%s%%)" % (d.pk, fname, _n(card), _n(res["margin"]), res["margin_pct"]))
                for k in ("revenue",) + S.COST_KEYS:
                    s = res["sources"].get(k) or {}
                    self.stdout.write("      %-13s %10s  [%s] %s" % (k, _n(res[k]), s.get("kind"), s.get("uk", "")))

        hdr = "| Воронка | Угод | Виручка | Маржа зараз (картка) | % | Собівартість | Доставка | Комісія | Пакування | Майстри+транспорт | Повернення | Маржа нова | % | Δ п.п. | з них оцінкою |"
        self.stdout.write("")
        self.stdout.write(hdr)
        self.stdout.write("|" + "---|" * 15)
        order = sorted((k for k in agg if k), key=lambda k: -agg[k]["revenue"]) + [""]
        for k in order:
            a = agg[k]
            rev = a["revenue"] or Decimal("0")
            p0 = (a["card"] / rev * 100) if rev else Decimal("0")
            p1 = (a["margin"] / rev * 100) if rev else Decimal("0")
            self.stdout.write("| %s | %d | %s | %s | %.1f | %s | %s | %s | %s | %s | %s | **%s** | **%.1f** | %+.1f | %s |" % (
                k or "**Разом**", a["n"], _n(rev), _n(a["card"]), p0, _n(a["cogs"]), _n(a["delivery"]), _n(a["commission"]),
                _n(a["packaging"]), _n(a["master_works"]), _n(a["returns"]), _n(a["margin"]), p1, p1 - p0, _n(a["est"])))
        if cheap_sender:
            self.stdout.write("\nДоставка за наш рахунок, угода < 6000 ₴ (%d):" % len(cheap_sender))
            for pk, amt, dl, note in cheap_sender:
                self.stdout.write("  %s · сума %s ₴ · доставка %s ₴ · %s" % (CRM_URL % pk, _n(amt), _n(dl), note))
        if flagged:
            self.stdout.write("\nПеревірити (%d):" % len(flagged))
            for pk, text in flagged:
                self.stdout.write("  #%s %s" % (pk, text))
        if live:
            self.stdout.write("\nLIVE: збережено %d, закриті (locked) не чіпали: %d%s" % (
                saved, locked_skip, ", закрито --lock" if o["lock"] else ""))
        else:
            self.stdout.write("\nDRY: нічого не записано. Далі: --live --limit 2, потім --live.")
