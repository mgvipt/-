"""KPI складу (рішення Олега 15.09.2026: «KPI складу ок, я затверджую») — нові версії ставок комірників з 01.10.2026.

  python manage.py payroll_wh_kpi_apply             # те саме, що --dry
  python manage.py payroll_wh_kpi_apply --dry       # «було → стане», приклади ЗП (100% і 80%), підказка CRM за 2 місяці.
                                                    # НІЧОГО не пише в БД (лише читання; приклади рахуються в памʼяті)
  python manage.py payroll_wh_kpi_apply --live      # створити НОВІ версії — через SchemeSaveView, тобто рівно як кнопка
                                                    # «Зберегти як нову версію»: стара діє до 30.09, вересень і раніше
                                                    # не змінюються; запис в «Історії змін» (PayRateLog new_version)
Опції:
  --from 2026-10-01               з якого місяця нова версія (лише 1-ше число)
  --larionova 4400/2600           спліт для Ілони Ларіонової (user 127): 4400/2600 (за замовчуванням) або 4375/2625
  --base base_by_days             «за вихід» по табелю (як затверджено) або fixed_monthly (фіксовано, без табеля)
  --by <логін>                    від чийого імені запис у --live (за замовчуванням director / перший суперкористувач)
  --plan "102:5000:3000,127:4400:2600"   хто і скільки (для тестів); --today YYYY-MM-DD; --no-suggest
Повторний --live нічого не дублює: якщо версія з 01.10 уже є — пропускає.
"""
import copy
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.payroll import engine
from apps.payroll.models import PayComponent, PayRateLog, PayScheme
from apps.payroll.wh_kpi import WH_STANDARD_CRITERIA, suggest_wh_standard

DEFAULT_PLAN = "102:5000:3000,127:4400:2600"
EXPECTED_SCHEME = {102: 6, 127: 7}   # прод 15.09: Інна Романенко — #6, Ілона Ларіонова — #7
NEW_TITLE = "За вихід + стандарт складу + відрядно"
NOTE = ("KPI складу — рішення Олега 15.09.2026: тверда частина = за вихід (по табелю) + стандарт складу × оцінка місяця "
        "(8 пунктів: 1, 4, 5, 6 рахує CRM, 2, 3, 7, 8 відмічає керівник). Відрядні ставки без змін.")
MONTHS = ["", "січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень", "вересень",
          "жовтень", "листопад", "грудень"]
n = engine._n


def _label(period):
    return f"{MONTHS[int(period[5:7])]} {period[:4]}"


def _parse_plan(s):
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            uid, a, b = part.split(":")
            out.append((int(uid), float(a), float(b)))
        except ValueError:
            raise CommandError(f"--plan: «{part}» — треба user:за_вихід:стандарт")
    return out


def _comp_text(c):
    p = c.get("params") or {}
    k = c["kind"]
    if k in ("base_by_days", "fixed_monthly"):
        return f"{n(p.get('amount'))} ₴" + (" × відпрацьовані дні табеля / робочі дні місяця" if k == "base_by_days" else " щомісяця")
    if k == "standard":
        return f"до {n(p.get('max'))} ₴ × оцінка місяця" + (f" ({len(p.get('criteria') or [])} пунктів)" if p.get("criteria") else "")
    if k == "piece_rate":
        return "за ставками складу (без змін)"
    return str(p)


class Command(BaseCommand):
    help = "KPI складу: нові версії ставок комірників з 01.10.2026 (--dry за замовчуванням; --live — записати)"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--from", dest="vfrom", default="2026-10-01")
        parser.add_argument("--plan", default=DEFAULT_PLAN)
        parser.add_argument("--larionova", default="")
        parser.add_argument("--base", default="base_by_days", choices=["base_by_days", "fixed_monthly"])
        parser.add_argument("--by", default="")
        parser.add_argument("--today", default="")
        parser.add_argument("--no-suggest", action="store_true")

    # ─────────── приклади ЗП в памʼяті (без запису) — ті самі функції рушія, що й engine.calc ───────────
    def _example(self, u, cur, comps, period, score, vfrom):
        pol = engine.policy()
        d1, d2 = engine.period_bounds(period)
        sc = PayScheme(user=u, position=cur.position, valid_from=vfrom, employment=cur.employment)
        sc._preview = not (vfrom <= d2)   # як engine.calc: схема на місяць, коли ще не діяла, — «приклад» на даних того місяця
        lines = []
        for c in comps:
            obj = PayComponent(kind=c["kind"], title=c["title"], params=copy.deepcopy(c["params"]))
            if c["kind"] == "base_by_days":
                lines.append(engine._c_base(sc, obj, u, d1, d2, pol))
            elif c["kind"] == "fixed_monthly":
                lines.append(engine._c_fixed(sc, obj, d1, d2))
            elif c["kind"] == "standard":
                obj.params["scores"] = {period: score}
                lines.append(engine._c_standard(obj, period)[0])
            elif c["kind"] == "piece_rate":
                lines.append(engine._c_piece(obj, u, d1, d2))
        try:  # «Задачі з біржі» — як у engine.calc (лише читання)
            from apps.bounty.payroll import payroll_line
            bl = payroll_line(u, period)
            if bl:
                lines.append(bl)
        except ImportError:
            pass
        return lines, sum(l["amount"] for l in lines)

    @staticmethod
    def _fmt_lines(lines):
        return " + ".join(f"{l['title'].split(' (')[0].lower()} {n(l['amount'])}" + (f" ({l['detail']})" if l["kind"] == "base_by_days" else "")
                          for l in lines)

    def handle(self, *args, **o):
        if o["dry"] and o["live"]:
            raise CommandError("Або --dry, або --live")
        live = bool(o["live"])
        w = self.stdout.write
        vfrom = date.fromisoformat(o["vfrom"])
        if vfrom.day != 1:
            raise CommandError("Нова версія — лише з 1-го числа місяця")
        prev_day = vfrom - timedelta(days=1)
        today = date.fromisoformat(o["today"]) if o["today"] else None
        plan = _parse_plan(o["plan"])
        if o["larionova"]:
            try:
                a, b = (float(x) for x in o["larionova"].split("/"))
            except ValueError:
                raise CommandError("--larionova 4400/2600")
            plan = [(uid, a, b) if uid == 127 else (uid, x, y) for uid, x, y in plan]
        base_kind = o["base"]
        U = get_user_model()
        w("=" * 100)
        w(("РЕЖИМ LIVE — СТВОРЮЮ нові версії" if live else "РЕЖИМ DRY — нічого не записую (лише читання)")
          + f"; нова версія з {vfrom:%d.%m.%Y}, стара діятиме до {prev_day:%d.%m.%Y}; «за вихід» = {base_kind}")
        w("=" * 100)
        periods = [engine.add_months(vfrom, -2).strftime("%Y-%m"), engine.add_months(vfrom, -1).strftime("%Y-%m"), vfrom.strftime("%Y-%m")]
        todo = []
        for uid, base_amt, std_max in plan:
            u = U.objects.filter(pk=uid).first()
            if not u:
                w(f"\nuser {uid}: не знайдено — пропускаю")
                continue
            who = u.get_full_name() or u.username
            cur = engine.active_scheme(u, prev_day)
            w(f"\n── {who} (user {uid}) " + "─" * 60)
            if not cur:
                w(f"  ПРОПУСК: немає діючої схеми на {prev_day:%d.%m.%Y}")
                continue
            problems = []
            if EXPECTED_SCHEME.get(uid) and cur.id != EXPECTED_SCHEME[uid] and "--plan" not in str(o.get("plan_explicit", "")):
                w(f"  УВАГА: очікувалась схема #{EXPECTED_SCHEME[uid]}, діє #{cur.id} — перевірте")
            cur_comps = list(cur.components.filter(active=True))
            kinds = sorted(c.kind for c in cur_comps)
            if kinds != ["fixed_monthly", "piece_rate"]:
                problems.append(f"склад схеми вже інший ({', '.join(kinds)}) — не чіпаю, дивитись вручну")
            later = (PayScheme.objects.filter(user=u, purpose="official", valid_from__gte=vfrom).exclude(status="archived")
                     .order_by("valid_from").first())
            if later:
                problems.append(f"уже є версія з {later.valid_from:%d.%m.%Y} (схема #{later.id}) — повторно не створюю")
            w(f"  БУЛО: схема #{cur.id} «{cur.title}», {cur.position}, {cur.get_employment_display()}, діє з {cur.valid_from:%d.%m.%Y}"
              + (f" до {cur.valid_to:%d.%m.%Y}" if cur.valid_to else " (без кінця)"))
            for c in cur_comps:
                w(f"     · {c.get_kind_display()} «{c.title}»: {_comp_text({'kind': c.kind, 'params': c.params})}")
            piece = next((c for c in cur_comps if c.kind == "piece_rate"), None)
            comps = [
                {"kind": base_kind, "title": "За вихід (по табелю)" if base_kind == "base_by_days" else "Ставка за місяць",
                 "params": {"amount": base_amt}, "active": True},
                {"kind": "standard", "title": f"Стандарт складу (до {n(std_max)} ₴, 8 пунктів)",
                 "params": {"max": std_max, "criteria": copy.deepcopy(WH_STANDARD_CRITERIA)}, "active": True},
                {"kind": "piece_rate", "title": piece.title if piece else "Відрядно (ставки складу)",
                 "params": copy.deepcopy(piece.params or {}) if piece else {}, "active": True},
            ]
            w(f"  СТАНЕ: НОВА версія з {vfrom:%d.%m.%Y} «{NEW_TITLE}» (схема #{cur.id} діятиме до {prev_day:%d.%m.%Y}):")
            for c in comps:
                w(f"     · {c['title']}: {_comp_text(c)}")
            for i, c in enumerate(WH_STANDARD_CRITERIA, 1):
                w(f"         {i}. {c['title']} — {c['target']} [{'вимірює CRM' if c['how_measured'] == 'auto' else 'відмічає керівник'}]")
            fixed_old = sum(float((c.params or {}).get("amount") or 0) for c in cur_comps if c.kind == "fixed_monthly")
            w(f"     тверда частина: було {n(fixed_old)} ₴ → стане {n(base_amt)} + {n(std_max)} = {n(base_amt + std_max)} ₴ (при оцінці 100% і повному табелі)")
            w("  ПРИКЛАДИ «на руки» (без запису; реальні табель і відрядні записи того місяця):")
            tday = today or timezone.localdate()
            for per in periods:
                now = engine.calc(u, per)
                p1, p2 = engine.period_bounds(per)
                tag = (" (ще не почався — табеля немає, «за вихід» за календарем)" if p1 > tday
                       else " (місяць ще йде — табель і відрядні по сьогодні)" if p2 >= tday
                       else " (довідково — повний місяць табеля)" if per == periods[0] else "")
                w(f"   {_label(per)}{tag}:")
                w(f"     зараз (схема #{(now.get('scheme') or {}).get('id')}): {self._fmt_lines(now['lines'])} = {n(now['total'])} ₴")
                for score in (1.0, 0.8):
                    lines, tot = self._example(u, cur, comps, per, score, vfrom)
                    w(f"     нова, оцінка {round(score * 100)}%: {self._fmt_lines(lines)} = {n(tot)} ₴")
            if base_kind == "base_by_days":
                from apps.finance.models import WorkDay
                for per in periods[:2]:
                    d1, d2 = engine.period_bounds(per)
                    wd = WorkDay.objects.filter(user=u, date__gte=d1, date__lte=d2, status__in=["worked", "overtime"]).count()
                    till = " (по сьогодні)" if d2 >= (today or timezone.localdate()) else ""
                    w(f"   табель {_label(per)}{till}: {wd} змін при нормі {engine.workdays(d1, d2)} робочих днів пн–пт "
                      f"→ «за вихід» {n(base_amt * min(wd, engine.workdays(d1, d2)) / (engine.workdays(d1, d2) or 1))} ₴ з {n(base_amt)}")
            if problems:
                for p in problems:
                    w(f"  ПРОПУСК: {p}")
            else:
                todo.append((u, cur, comps))

        if not o["no_suggest"]:
            w("\n" + "=" * 100)
            w("ПІДКАЗКА CRM по стандарту складу (лише читання) — пункти 1, 4, 5, 6; 2, 3, 7, 8 за замовчуванням «так»")
            for uid, _a, std_max in plan:
                u = U.objects.filter(pk=uid).first()
                if not u:
                    continue
                for per in periods[:2]:
                    r = suggest_wh_standard(u, per, None, today=today)
                    w(f"\n  {r['user_name']} — {_label(per)} (дні {r['from']} … {r['to'] or '—'}; робочих днів: {r['workdays']}, {r['workdays_source']})")
                    for p in r["points"]:
                        if p["how_measured"] == "auto":
                            verdict = {True: "так", False: "НІ", None: "немає даних"}[p["pass"]]
                            w(f"    {p['n']}. {p['title']}: {p['value_text']} (мета {p['target']}) → {verdict}")
                            for dline in p["details"][:6]:
                                w(f"         · {dline}")
                            if len(p["details"]) > 6:
                                w(f"         · … ще {len(p['details']) - 6}")
                        else:
                            w(f"    {p['n']}. {p['title']}: відмічає керівник (так за замовчуванням). {p['hint']}")
                    w(f"    → підказана оцінка {r['good']} з {len(r['points'])} = {r['suggested_pct']}% "
                      f"→ стандарт {n(std_max)} × {r['suggested_pct']}% = {n(std_max * r['suggested_pct'] / 100)} ₴")

        w("\n" + "=" * 100)
        if not live:
            w(f"DRY: нічого не записано. До створення готово: {len(todo)} з {len(plan)}. Записати: --live")
            return
        if not todo:
            w("LIVE: нічого створювати (див. ПРОПУСК вище).")
            return
        from rest_framework.test import APIRequestFactory, force_authenticate
        from apps.payroll.views import SchemeSaveView
        if o["by"]:
            by = U.objects.filter(username=o["by"]).first()
        else:
            by = (U.objects.filter(username="director", is_superuser=True).first()
                  or U.objects.filter(is_superuser=True, is_active=True).order_by("id").first())
        if not by:
            raise CommandError("Не знайдено власника для запису (--by <логін>)")
        rf = APIRequestFactory()
        view = SchemeSaveView.as_view()
        with transaction.atomic():   # обидві людини — або разом, або ніхто
            for u, cur, comps in todo:
                body = {"valid_from": vfrom.isoformat(), "position": cur.position, "department": cur.department,
                        "title": NEW_TITLE, "employment": cur.employment, "note": NOTE, "options": cur.options or {},
                        "components": comps}
                req = rf.post(f"/api/payroll/schemes/{cur.id}/save/", body, format="json")
                force_authenticate(req, user=by)
                resp = view(req, pk=cur.id)
                if resp.status_code != 200:
                    raise CommandError(f"{u}: SchemeSaveView відповів {resp.status_code}: {getattr(resp, 'data', '')}")
                new = PayScheme.objects.get(pk=resp.data["id"])
                cur.refresh_from_db()
                if new.valid_from != vfrom or cur.valid_to != prev_day or new.id == cur.id:
                    raise CommandError(f"{u}: неочікуваний результат (нова #{new.id} з {new.valid_from}, стара до {cur.valid_to}) — відкат")
                logs = PayRateLog.objects.filter(scheme=new, action="new_version").count()
                w(f"LIVE: {u.get_full_name() or u.username}: створено схему #{new.id} з {new.valid_from:%d.%m.%Y}; "
                  f"#{cur.id} діє до {cur.valid_to:%d.%m.%Y}; «Історія змін»: {logs} запис(и); від імені {by.username}")
        w("LIVE: готово. Вересень і раніше не змінено (рахуються за старою версією).")
