"""«Моя ЗП і KPI» та «KPI угоди» — кожен бачить ЛИШЕ СВОЇ дані (рішення Олега 14.09.2026, пакет my-kpi).

Що віддає:
- GET /api/payroll/my/?period=YYYY-MM — моя ЗП за місяць: рядки (затверджена відомість або розрахунок наживо),
  схема простими словами, план, стандарт, гарантія з умовами, «що ще можна заробити» (тест-набори без основного
  замовлення зі строками 300/200/100 ₴), для складу — відрядні записи за місяць по типах.
- GET /api/payroll/my/?only=rules — лише правила «Як виконати план і умови ЗП» (сторінка «Розвиток», #plan), без розрахунку.
- GET /api/payroll/deal-kpi/<deal_id>/ — «Ваш заробіток з угоди зараз / можна до» і чек-лист саме цієї угоди.

Правила:
- лише request.user; параметр user=<чужий id> → 403; ставок інших людей не віддаємо;
- суму і % маржі угоди не віддаємо в цих відповідях нікому (маржу бачить власник у своєму блоці з правом deal.margin.view);
  з пояснення до «% з маржі» у ЗП прибираємо «маржа N ₴», якщо немає права deal.margin.view;
- лише читання: apps.payroll.engine (calc, active_scheme, deal_bonus_preview, deal_margin, policy) і runs.active_run.
  Жодного запису в БД, жодних повідомлень клієнтам.
"""
import re
from datetime import timedelta

from django.db.models import Count, F, Min, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine

MONTHS = ["", "січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
          "вересень", "жовтень", "листопад", "грудень"]
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# engine._c_margin пише «оплати 10 000 ₴ по 3 угодах  маржа 5 000 ₴» (коми замінено пробілами) — суму маржі прибираємо
_MARGIN_NUM = re.compile(r"[,\s]+маржа\s+[\d\s ]+₴")

DISCOUNT_ARTICLE = "Знижка без бонусу"   # FinModelArticle (config) «Знижка без бонусу-маржі від (%)», на проді id 77 = 15%
DISCOUNT_DEFAULT = 15.0
# Памʼятка «Умови доставки» (QuickReply 59, KB 666, 13.09.2026)
FREE_THIN_FROM = 6000
FREE_TEXTURED_FROM = 20000
THIN_SHARE_MIN = 0.70
TEXTURED_KEYS = ("pattera", "slate", "травертин", "travertin", "марморин", "marmorin")
PAINT_KEYS = ("primalex", "play&clean", "play & clean", "balakryl", "balacryl", "ivc ")
THIN_KEYS = ("шовк", "silk", "galateya", "галате", "celestia", "velvet", "вельвет", "velora", "perla", "mio ",
             "iridis", "lumina", "gaia", "siera", "sirena", "eleganti", "перламутр")
SUPPORT_KEYS = ("primer", "грунт", "ґрунт", "protection", "second layer", "fondo", "підклад", "тонер", "toner",
                "послуга тонування")
TEST_FOCUS_DAYS = 30     # «тест-набори, оплачені за останні 30 днів, без основного замовлення»
TEST_OLDER_DAYS = 180    # старші — лише лічильник «ще N клієнтів»

STANDARD_SALES = [
    "Швидкість: у робочий час відповідь клієнту до 15 хвилин — щонайменше у 80% чатів.",
    "Кожен закритий чат — з позначкою якості й причиною; жодного чату, закритого без відповіді клієнту.",
    "Дожими за правилом: 1-й — через 2 дні особисто, 2-й — теплим повідомленням через 4–5 днів.",
    "Пропущені дзвінки — передзвонити до 15 хвилин у робочий час.",
    "Потреби клієнта заповнені: тип приміщення, площа, матеріал, бюджет (блок «Виявлення потреби»).",
]
STANDARD_WHERE = [
    "«Чати · Відкриті лінії» — швидкість відповіді і закриття чату з позначкою якості.",
    "«Телефонія» — пропущені дзвінки і передзвони.",
    "«Задачі» — дожими і нагадування (кнопка «+ Задача» в картці).",
    "Картка ліда / угоди → блок «Виявлення потреби».",
]


# ─────────────────────────── дрібні помічники ───────────────────────────

def _can(u, code):
    return bool(u and u.is_authenticated and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(code))))


def _n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(x):
    return f"{int(round(_n(x))):,}".replace(",", " ")


def _date_of(v):
    if not v:
        return None
    if hasattr(v, "hour"):
        return timezone.localtime(v).date() if timezone.is_aware(v) else v.date()
    return v


def _iso(v):
    v = _date_of(v)
    return v.isoformat() if v else None


def _dm(v):
    v = _date_of(v)
    return v.strftime("%d.%m.%Y") if v else ""


def _who(u):
    return (u.get_full_name() or u.username) if u else ""


def _label(period):
    return f"{MONTHS[int(period[5:7])]} {period[:4]}"


def _periods(today):
    cur = today.strftime("%Y-%m")
    prev = engine.add_months(today.replace(day=1), -1).strftime("%Y-%m")
    return cur, prev


def _funnel_names(ids):
    from apps.crm.models import Funnel
    ids = list(ids or [])
    names = dict(Funnel.objects.filter(id__in=ids).values_list("id", "name"))
    return ", ".join(names.get(i, f"#{i}") for i in ids)


def _tiers(p):
    t = {"fast_days": 30, "min_order": 3000, "fast": 300, "slow": 200, "small": 100}
    t.update((p or {}).get("tiers") or {})
    return t


def _margin_params(p, pol):
    p = p or {}
    to = _n(p.get("pct_to_plan", 10))
    return {"funnels": p.get("funnels") or pol["funnels"]["online"], "to": to,
            "over": _n(p.get("pct_over_plan", to)), "gate": round(_n(p.get("gate_standard_min", 0.75)) * 100)}


def _line_out(l, can_margin):
    out = {"kind": l.get("kind"), "title": l.get("title") or "", "amount": int(round(_n(l.get("amount")))),
           "rate": l.get("rate"), "detail": l.get("detail") or "", "warn": l.get("warn") or "",
           "estimate": bool(l.get("estimate"))}
    if l.get("kind") == "margin_share" and not can_margin:
        out["detail"] = _MARGIN_NUM.sub("", out["detail"])  # «маржа N ₴» — суму маржі менеджеру не віддаємо
    return out  # basis (для «% з маржі» це сума маржі) не віддаємо взагалі


# ─────────────────────────── схема простими словами і правила ───────────────────────────

def _part_plain(c, pol):
    p = c.params or {}
    k = c.kind
    if k == "base_by_days":
        txt = (f"За вихід: {_fmt(p.get('amount'))} ₴ на місяць при повному табелі. Менше днів — пропорційно; "
               "вихід у вихідний (перевиконання) — плюс денна ставка.")
    elif k == "fixed_monthly":
        txt = f"Фіксована оплата: {_fmt(p.get('amount'))} ₴ на місяць (неповний місяць — пропорційно)."
    elif k == "standard":
        txt = (f"Стандарт роботи: до {_fmt(p.get('max'))} ₴. Раз на місяць керівник ставить оцінку стандарту "
               f"(0–100%) — стільки відсотків від {_fmt(p.get('max'))} ₴ ви й отримуєте.")
    elif k == "margin_share":
        m = _margin_params(p, pol)
        txt = (f"{m['to']:g}% з маржі ваших оплачених угод (воронки: {_funnel_names(m['funnels'])}) до плану місяця; "
               f"з частини понад план — {m['over']:g}%, якщо оцінка стандарту не нижче {m['gate']}%. "
               "Рахуються гроші, що прийшли цього місяця, а не сума угоди.")
    elif k == "revenue_share":
        pct = _n(p.get("pct"))
        b = p.get("basis", "funnels")
        if b == "object_acts":
            txt = f"{pct:g}% від усієї суми акту обʼєкта — нараховується в місяць, коли акт закрито."
        elif b == "objects_income":
            txt = f"{pct:g}% з приходів напрямку «Обʼєкти» (без угод)."
        elif b == "own_payments":
            txt = f"{pct:g}% з оплат по ваших угодах."
        else:
            own = p.get("own_only", True)
            txt = f"{pct:g}% з оплат {'по ваших угодах ' if own else ''}у воронках: {_funnel_names(p.get('funnels') or [])}."
    elif k == "event_bonus":
        t = _tiers(p)
        txt = (f"Бонус «тест-набір → основне»: +{_fmt(t['fast'])} ₴, якщо клієнт оплатив перше основне замовлення "
               f"не пізніше {t['fast_days']} днів після оплати тест-набору; +{_fmt(t['slow'])} ₴ — якщо пізніше; "
               f"+{_fmt(t['small'])} ₴ — якщо основне замовлення менше {_fmt(t['min_order'])} ₴. "
               "Раз на клієнта; отримує відповідальний за основну угоду.")
    elif k == "guarantee":
        s, e = engine.guarantee_window(c)
        amt = _n(p.get("amount") or pol["guarantee"]["amount"])
        per = f" з {s:%d.%m.%Y} по {e:%d.%m.%Y}" if s else ""
        txt = (f"Гарантія новачку: {_fmt(amt)} ₴ на місяць{per}. Якщо за схемою вийшло менше — доплата до гарантії, "
               "але лише після того, як керівник підтвердить умови за місяць.")
    elif k == "piece_rate":
        txt = ("Відрядно (склад): кожна дія — окремий запис за ставками складу: вага відвантаження, пакування, "
               "тонування, робочий день. Помилка чи невірний матеріал — утримання.")
    else:
        txt = ""
    return {"kind": k, "title": c.title or c.get_kind_display(), "plain": txt}


def _scheme_out(sc, pol):
    if not sc:
        return None
    return {"position": sc.position, "title": sc.title, "valid_from": sc.valid_from.isoformat(),
            "parts": [_part_plain(c, pol) for c in sc.components.filter(active=True)]}


def _rules(sc, pol):
    """«Як виконати план і умови ЗП» — з ВАШОЇ схеми: що потрібно для кожної частини і куди дивитись у CRM."""
    comps = list(sc.components.filter(active=True)) if sc else []
    kinds = {c.kind for c in comps}
    sales = bool(kinds & {"margin_share", "event_bonus"})
    out = []
    for c in comps:
        p = c.params or {}
        k = c.kind
        if k == "base_by_days":
            out.append({"kind": k, "title": "За вихід (табель)", "need": [
                "Кожен день має бути в табелі: відпрацьований, вихідний, лікарняний чи відпустка.",
                "Прогул зменшує оплату за вихід і може зняти гарантію новачку.",
                "Вийшли у вихідний на прохання керівника — це «перевиконання»: плюс денна ставка."],
                "where": ["«Фінанси → Табель» (якщо розділ не відкривається — табель веде керівник)."]})
        elif k == "fixed_monthly":
            out.append({"kind": k, "title": c.title or "Фіксована оплата", "need": [
                "Сума не залежить від продажів; неповний місяць — пропорційно дням роботи."], "where": []})
        elif k == "standard":
            need = [f"Що входить у ваш стандарт: {c.title}."] if c.title else []
            need += STANDARD_SALES if sales else ["Деталі стандарту для вашої посади — у керівника."]
            need.append(f"Оцінку ставить керівник раз на місяць: 100% — повна сума до {_fmt(p.get('max'))} ₴. "
                        "Поки оцінки немає, у розрахунку стоїть 100%.")
            mc = next((x for x in comps if x.kind == "margin_share"), None)
            if mc:
                need.append(f"Оцінка стандарту від {_margin_params(mc.params, pol)['gate']}% відкриває підвищену ставку понад план.")
            out.append({"kind": k, "title": "Стандарт роботи", "need": need, "where": STANDARD_WHERE if sales else []})
        elif k == "margin_share":
            m = _margin_params(p, pol)
            out.append({"kind": k, "title": "% з маржі продажів", "need": [
                f"Рахуються лише гроші, що прийшли по ваших угодах (воронки: {_funnel_names(m['funnels'])}) цього місяця.",
                f"До плану — {m['to']:g}%, з частини понад план — {m['over']:g}%.",
                f"Щоб отримати {m['over']:g}% понад план, оцінка стандарту має бути не нижче {m['gate']}%.",
                "Знижка зменшує ваш заробіток: кожна гривня знижки — мінус з вашої частки. Замість знижки пропонуйте "
                "безкоштовну доставку від порогу, запас матеріалу або захисне покриття.",
                "Без плану на місяць усе рахується за ставкою до плану."],
                "where": ["Картка угоди → «Ваш заробіток з угоди»: скільки зараз і скільки можна.",
                          "«Розвиток» → «Моя ЗП і KPI»: прогрес плану."]})
        elif k == "revenue_share":
            b = p.get("basis", "funnels")
            need = [_part_plain(c, pol)["plain"]]
            where = []
            if b == "object_acts":
                need.append("Акт обʼєкта вносить і закриває власник; нарахування — у місяці закриття акту.")
                where.append("Акти обʼєктів — у керівника (закриває лише власник).")
            else:
                need.append("Рахуються оплати, що прийшли в журнал цього місяця.")
                where.append("Картка угоди → історія платежів.")
            out.append({"kind": k, "title": c.title or "% з оплат", "need": need, "where": where})
        elif k == "event_bonus":
            t = _tiers(p)
            out.append({"kind": k, "title": "Бонус «тест-набір → основне»", "need": [
                "Відлік — від дати оплати тест-набору.",
                f"До {t['fast_days']} днів → +{_fmt(t['fast'])} ₴; пізніше → +{_fmt(t['slow'])} ₴; "
                f"основне менше {_fmt(t['min_order'])} ₴ → +{_fmt(t['small'])} ₴.",
                "Через 2–3 дні після того, як клієнт отримав набір, — напишіть або подзвоніть: «Як вам зразок? Вийшло нанести?»",
                "Поставте задачу-нагадування в картці тест-набору (кнопка «+ Задача»), щоб клієнт не випав з фокусу.",
                "Бонус — раз на клієнта; отримує відповідальний за основну угоду."],
                "where": ["«Розвиток» → «Моя ЗП і KPI» → «Що ще можна заробити»: клієнти і строки.",
                          "Картка тест-набору → «Ваш заробіток з угоди»."]})
        elif k == "guarantee":
            conds = list(p.get("conditions") or engine.GUARANTEE_CONDITIONS)
            out.append({"kind": k, "title": "Гарантія новачку",
                        "need": conds + ["Доплата до гарантії — лише коли керівник підтвердить умови за місяць."],
                        "where": ["«Розвиток» → «Моя ЗП і KPI» → «Гарантія»: які умови вже підтверджено."]})
        elif k == "piece_rate":
            out.append({"kind": k, "title": "Відрядно (склад)", "need": [
                "Кожна дія складу — окремий запис: вага відвантаження, пакування, тонування, робочий день.",
                "Помилка чи невірний матеріал — утримання; бонус за ідею чи чистоту — окремим записом.",
                "Рахуються лише підтверджені записи."],
                "where": ["«Відвантаження» — ваші задачі складу.", "«Розвиток» → «Моя ЗП і KPI» → записи за місяць по типах."]})
    if sales:
        out.append({"kind": "plan", "title": "План місяця", "need": [
            "План на місяць ставить керівник (мінімум, норма, амбіція).",
            "Прогрес видно вгорі цієї сторінки — блок «Моя ЗП і KPI».",
            "Кожен тест-набір — майбутнє основне замовлення: тримайте клієнта у фокусі.",
            "Прорахунок по площі — кожному, хто назвав площу або надіслав фото.",
            f"Замість знижки — безкоштовна доставка від порогу (тонкошарові від {_fmt(FREE_THIN_FROM)} ₴, "
            f"фактурні від {_fmt(FREE_TEXTURED_FROM)} ₴)."],
            "where": ["«Фінанси → Плани» (якщо є доступ) або у керівника."]})
        out.append({"kind": "company", "title": "Правило компанії", "need": [
            "Раз на квартал власник звіряє ЗП відділу продажів із маржею компанії. ЗП за місяць не ріжуть — "
            "розбирають причини і правлять ставки з наступного кварталу.",
            "Тут ви бачите лише свої цифри; цифри інших людей не показуються."], "where": []})
    out.append({"kind": "ask", "title": "Куди звертатись", "need": [
        "Питання по ЗП, плану чи оцінці стандарту — до керівника.",
        "Бачите помилку в цифрах — напишіть керівнику номер угоди або дату."], "where": []})
    return out


# ─────────────────────────── блоки «Моєї ЗП» ───────────────────────────

def _plan_out(u, period, comps, pol):
    from apps.finance.models import ManagerPlan
    mc = next((c for c in comps if c.kind == "margin_share"), None)
    p = ManagerPlan.objects.filter(user=u, period=period).first()
    if not mc and not p:
        return None
    d1, d2 = engine.period_bounds(period)
    flt = {"deal__owner": u}
    m = _margin_params(mc.params, pol) if mc else None
    if m:
        flt["deal__funnel_id__in"] = m["funnels"]
    fact = _n(engine._income(d1, d2, **flt).aggregate(s=Sum("amount_uah"))["s"])
    target = _n(p.target_revenue) if p else 0.0
    out = {"fact": round(fact), "target": round(target),
           "min": round(_n(p.min_revenue)) if p else 0, "ambition": round(_n(p.ambition_revenue)) if p else 0,
           "pct": round(fact / target * 100) if target else None,
           "left": round(max(0.0, target - fact)) if target else None,
           "over": round(max(0.0, fact - target)) if target else 0,
           "basis": "оплати по ваших угодах" + (f" (воронки: {_funnel_names(m['funnels'])})" if m else "")}
    if m:
        out.update({"to_pct": m["to"], "over_pct": m["over"], "gate_pct": m["gate"]})
    if not target:
        out["note"] = "План на цей місяць ще не встановлено — усе рахується за ставкою до плану."
    return out


def _standard_out(comps, period, lines):
    c = next((x for x in comps if x.kind == "standard"), None)
    if not c:
        return None
    sc = ((c.params or {}).get("scores") or {}).get(period)
    ln = next((l for l in lines if l.get("kind") == "standard"), None)
    return {"title": c.title, "max": round(_n((c.params or {}).get("max"))), "set": sc is not None,
            "score_pct": round(_n(sc) * 100) if sc is not None else None,
            "amount": int(round(_n(ln.get("amount")))) if ln else None}


def _guarantee_out(comps, period, lines, pol):
    c = next((x for x in comps if x.kind == "guarantee"), None)
    if not c:
        return None
    p = c.params or {}
    s, e = engine.guarantee_window(c)
    d1, d2 = engine.period_bounds(period)
    active = bool(s) and not (d2 < s or d1 > e)
    chk = (p.get("checks") or {}).get(period) or {}
    items = chk.get("items") if isinstance(chk.get("items"), list) else None  # на майбутнє: відмітки по кожній умові
    rows = []
    for i, text in enumerate(p.get("conditions") or engine.GUARANTEE_CONDITIONS):
        if items is not None and i < len(items):
            ok = bool(items[i])
        elif chk.get("ok"):
            ok = True
        else:
            ok = None
        rows.append({"text": text, "ok": ok})
    ln = next((l for l in lines if l.get("kind") == "guarantee"), None)
    subtotal = sum(_n(l.get("amount")) for l in lines if l.get("kind") not in ("guarantee", "insurance"))
    topup = max(0.0, _n(ln.get("basis")) - subtotal) if ln else 0.0
    return {"amount": round(_n(p.get("amount") or pol["guarantee"]["amount"])), "start": _iso(s), "end": _iso(e),
            "active": active, "confirmed": bool(chk.get("ok")), "checked": bool(chk), "note": chk.get("note") or "",
            "topup": round(topup), "paid_topup": int(round(_n(ln.get("amount")))) if ln else 0, "conditions": rows}


def _first_pays(deal_ids):
    from apps.finance.models import Transaction
    ids = [i for i in deal_ids if i]
    if not ids:
        return {}
    return {r["deal_id"]: r for r in Transaction.objects.filter(direction="in", transfer_account__isnull=True, deal_id__in=ids)
            .values("deal_id").annotate(first=Min("date"), total=Sum("amount_uah"))}


def _test_opportunities(u, ev, pol, today):
    """Мої тест-набори, оплачені за останні 30 днів, клієнт яких ще не оплатив основне замовлення."""
    from apps.crm.models import Contact, Deal
    t = _tiers(ev.params)
    mine = list(Deal.objects.filter(owner=u, funnel_id__in=pol["funnels"]["test"], contact__isnull=False)
                .values_list("id", "contact_id", "title"))
    fp = _first_pays([m[0] for m in mine])
    by_contact = {}
    for did, cid, title in mine:
        r = fp.get(did)
        if r and (cid not in by_contact or r["first"] < by_contact[cid][1]):
            by_contact[cid] = (did, r["first"], title)
    if not by_contact:
        return [], 0
    mains = list(Deal.objects.filter(contact_id__in=list(by_contact), funnel_id__in=pol["funnels"]["main"])
                 .values_list("id", "contact_id"))
    mfp = _first_pays([m[0] for m in mains])
    bought = {cid for did, cid in mains if did in mfp and mfp[did]["first"] >= by_contact[cid][1]}
    names = {}
    for c in Contact.objects.filter(id__in=list(by_contact)):
        names[c.id] = (" ".join(x for x in (c.first_name, c.last_name) if x) or getattr(c, "phone", "") or "")[:60]
    since, oldest = today - timedelta(days=TEST_FOCUS_DAYS), today - timedelta(days=TEST_OLDER_DAYS)
    rows, older = [], 0
    for cid, (did, first, title) in by_contact.items():
        if cid in bought:
            continue
        if first < since:
            older += 1 if first >= oldest else 0
            continue
        deadline = first + timedelta(days=int(t["fast_days"]))
        rows.append({"deal_id": did, "title": title, "client": names.get(cid, ""), "test_paid": first.isoformat(),
                     "deadline": deadline.isoformat(), "days_left": (deadline - today).days,
                     "fast": t["fast"], "slow": t["slow"], "small": t["small"], "min_order": t["min_order"]})
    rows.sort(key=lambda r: r["days_left"])
    return rows[:50], older


def _warehouse(u, d1, d2, only_if_any=False):
    try:
        from apps.warehouse.models import WarehousePayrollEntry as W
    except Exception:
        return None
    rows = list(W.objects.filter(employee=u, work_date__gte=d1, work_date__lte=d2, status="confirmed")
                .values("op_type").annotate(n=Count("id"), s=Sum("amount"), kg=Sum("quantity_kg")).order_by("op_type"))
    if not rows and only_if_any:
        return None
    labels = dict(W.OP)
    out = [{"op": r["op_type"], "label": labels.get(r["op_type"], r["op_type"]), "count": r["n"],
            "amount": round(_n(r["s"])), "kg": round(_n(r["kg"]), 1) if r["kg"] is not None else None} for r in rows]
    return {"rows": out, "total": round(sum(x["amount"] for x in out)), "from": d1.isoformat(), "to": d2.isoformat()}


def _more(b):
    """«Що ще можна заробити цього місяця» — лише з реальних даних."""
    out = []
    opps = b.get("opportunities") or []
    if opps:
        best = sum(int(o["fast"]) if o["days_left"] >= 0 else int(o["slow"]) for o in opps)
        o = opps[0]
        out.append({"code": "tests", "title": f"Тест-набори без основного замовлення: {len(opps)}", "amount": best,
                    "hint": f"Основне замовлення до строку — +{_fmt(o['fast'])} ₴ за клієнта (пізніше +{_fmt(o['slow'])} ₴, "
                            f"менше {_fmt(o['min_order'])} ₴ — +{_fmt(o['small'])} ₴). Список нижче."})
    pl = b.get("plan") or {}
    if pl.get("target"):
        rate = (f" Понад план ставка {pl['over_pct']:g}% замість {pl['to_pct']:g}% — при оцінці стандарту від {pl['gate_pct']}%."
                if pl.get("over_pct") and pl.get("over_pct") != pl.get("to_pct") else "")
        if pl.get("left"):
            out.append({"code": "plan", "title": f"До плану лишилось {_fmt(pl['left'])} ₴", "amount": None, "hint": rate.strip()})
        else:
            out.append({"code": "plan_over", "title": f"План виконано, понад план — {_fmt(pl['over'])} ₴", "amount": None,
                        "hint": ("Кожна оплата понад план —" + rate.split("Понад план ставка", 1)[-1]).strip() if rate else ""})
    st = b.get("standard") or {}
    if st and not st.get("set"):
        out.append({"code": "standard", "title": "Стандарт роботи ще не оцінено", "amount": st.get("max"),
                    "hint": "Дотримуйтесь правил стандарту — оцінка дає до повної суми. Правила — у «Як виконати план» нижче."})
    g = b.get("guarantee") or {}
    if g.get("active") and not g.get("confirmed") and g.get("topup"):
        out.append({"code": "guarantee", "title": "Доплата до гарантії чекає підтвердження умов", "amount": g["topup"],
                    "hint": "Керівник підтверджує умови в кінці місяця — перевірте список умов нижче."})
    return out


class MyPayrollView(APIView):
    """GET /api/payroll/my/?period=YYYY-MM[&only=rules] — лише дані того, хто питає (будь-який активний співробітник)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        q = request.query_params
        other = q.get("user") or q.get("user_id")
        if other not in (None, "") and str(other) != str(u.id):
            return Response({"detail": "Тут видно лише ваші власні дані"}, status=403)
        today = timezone.localdate()
        cur, prev = _periods(today)
        period = (q.get("period") or cur)[:7]
        if not PERIOD_RE.match(period):
            return Response({"detail": "Період — у форматі YYYY-MM"}, status=400)
        pol = engine.policy()
        d1, d2 = engine.period_bounds(period)
        sc = engine.active_scheme(u, d2)
        b = {"period": period, "period_label": _label(period),
             "periods": [{"value": p, "label": _label(p)} for p in (cur, prev)],
             "user_name": _who(u), "has_scheme": bool(sc), "is_current": period == cur,
             "links": [{"href": "/development#plan", "label": "Як виконати план — Розвиток"}]}
        if q.get("only") == "rules":
            b["scheme"] = _scheme_out(sc, pol)
            b["rules"] = _rules(sc, pol)
            return Response(b)
        if not sc:
            b.update({"message": "Для вас ще не задано ставку на цей місяць — розрахунок зʼявиться, щойно керівник її внесе. "
                                 "Питання — до керівника.",
                      "lines": [], "total": 0, "opportunities": [], "opp_older": 0, "more": [],
                      "warehouse": _warehouse(u, d1, d2, only_if_any=True)})
            return Response(b)
        from .models import PayrollPayout
        from .runs import active_run
        can_margin = _can(u, "deal.margin.view")
        live = engine.calc(u, period)
        run = active_run(u, period)
        if run:
            lines = run.lines or []
            paid = round(sum(_n(p.amount) for p in PayrollPayout.objects.filter(run__user_id=u.id, run__period=period)))
            b.update({"source": "approved", "approved_at": _iso(run.approved_at), "total": int(round(_n(run.total))),
                      "live_total": live["total"], "paid": paid, "remaining": int(round(_n(run.total))) - paid})
        else:
            lines = live["lines"]
            b.update({"source": "live", "total": live["total"]})
        b["lines"] = [_line_out(l, can_margin) for l in lines]
        seen, warns = set(), []
        for l in lines:
            w = l.get("warn") or ""
            if w and w not in seen:
                seen.add(w)
                warns.append(w)
        b["warnings"] = warns
        b["scheme"] = _scheme_out(sc, pol)
        comps = list(sc.components.filter(active=True))
        b["plan"] = _plan_out(u, period, comps, pol)
        b["standard"] = _standard_out(comps, period, lines)
        b["guarantee"] = _guarantee_out(comps, period, lines, pol)
        ev = next((c for c in comps if c.kind == "event_bonus"), None)
        if ev and period == cur:
            b["opportunities"], b["opp_older"] = _test_opportunities(u, ev, pol, today)
        else:
            b["opportunities"], b["opp_older"] = [], 0
        b["warehouse"] = _warehouse(u, d1, d2, only_if_any=not any(c.kind == "piece_rate" for c in comps))
        b["more"] = _more(b) if period == cur else []
        return Response(b)


# ─────────────────────────── KPI угоди ───────────────────────────

def _can_view_deal(u, deal):
    """Те саме правило, що в картці угоди (ScopedByRoleMixin): власник угоди, «всі угоди», стадії «бачу всі», спільна черга."""
    if u.is_superuser or (deal.owner_id and deal.owner_id == u.id):
        return True
    if not (hasattr(u, "has_perm_code") and u.has_perm_code("deal.view")):
        return False
    allowed = u.allowed_funnel_ids()
    if allowed is not None and deal.funnel_id not in allowed:
        return False
    if u.can_see_all_deals():
        return True
    va = u.viewable_all_stage_ids()
    if va is None or deal.stage_id in va:
        return True
    return deal.owner_id is None and getattr(deal.stage, "order", 1) == 0


def _received_at(deal):
    try:
        from apps.reviews.services import received_at_for
        return received_at_for(deal)
    except Exception:
        return None


def _discount_threshold():
    try:
        from apps.finance.models import FinModelArticle
        a = FinModelArticle.objects.filter(category="config", active=True, name__icontains=DISCOUNT_ARTICLE).first()
        if a is not None and _n(a.value) > 0:
            return _n(a.value)
    except Exception:
        pass
    return DISCOUNT_DEFAULT


def _item_name(i):
    return ((i.product.name if i.product_id else "") or i.custom_name or "").lower()


def _mat(i):
    n = _item_name(i)
    cat = (i.product.category.name if (i.product_id and i.product.category_id) else "").lower()
    if any(k in n for k in TEXTURED_KEYS):
        return "textured"
    if any(k in n for k in PAINT_KEYS):
        return "paint"
    if any(k in n for k in THIN_KEYS):
        return "thin"
    if any(k in n for k in SUPPORT_KEYS) or "тонер" in cat or "грунт" in cat:
        return "support"
    return "other"


def _is_tinted(i):
    n = _item_name(i)
    return "тонуван" in n and "без тонув" not in n


def _chk(code, status, title, hint="", where="", date=None):
    return {"code": code, "status": status, "title": title, "hint": hint, "where": where, "date": _iso(date)}


def _test_ctx(deal, pol, tiers):
    from apps.crm.models import Deal
    fp = _first_pays([deal.id]).get(deal.id)
    first = fp["first"] if fp else None
    main_paid = None
    if deal.contact_id and first:
        mids = list(Deal.objects.filter(contact_id=deal.contact_id, funnel_id__in=pol["funnels"]["main"]).values_list("id", flat=True))
        firsts = [r["first"] for r in _first_pays(mids).values() if r["first"] >= first]
        main_paid = min(firsts) if firsts else None
    return {"first": first, "main_paid": main_paid,
            "deadline": first + timedelta(days=int(tiers["fast_days"])) if first else None}


def _deal_earn(deal, sc, pol, items, kind, tctx, tiers):
    """Скільки заробить відповідальний: зараз (як у ЗП, до плану) і «можна до» (понад план, без зайвої знижки,
    бонус тест → основне). Лише суми ₴ — жодної маржі назовні."""
    prev = engine.deal_bonus_preview(deal)
    if prev is None:
        return None, 0.0
    now = _n(prev.get("total"))
    r, _est = engine.deal_margin(deal, pol)
    amount = _n(deal.amount)
    cost = amount * (1 - r)
    to_pct = _n(prev.get("margin_pct"))
    rev_pct = _n(prev.get("revenue_pct"))
    comps = list(sc.components.filter(active=True))
    mc = next((c for c in comps if c.kind == "margin_share" and deal.funnel_id in _margin_params(c.params, pol)["funnels"]), None)
    m = _margin_params(mc.params, pol) if mc else None
    over_pct = m["over"] if m else to_pct
    gross = max(sum(_n(i.base_sum) for i in items) if items else amount, amount)

    def bonus(x, mp):
        return max(0.0, x - cost) * mp / 100 + x * rev_pct / 100

    base = bonus(amount, to_pct)
    over_add = bonus(amount, over_pct) - base if over_pct > to_pct else 0.0
    disc_add = bonus(gross, to_pct) - base if gross > amount + 0.5 else 0.0
    parts = [{"code": "now", "label": "зараз (ставка до плану)", "amount": round(now)}]
    if over_add >= 1:
        parts.append({"code": "over", "label": f"якщо угода піде понад план місяця (ставка {over_pct:g}% замість {to_pct:g}%, "
                                                f"оцінка стандарту від {m['gate']}%)", "amount": round(over_add)})
    if disc_add >= 1:
        parts.append({"code": "discount", "label": "якщо без знижки на позиції", "amount": round(disc_add)})
    event = 0.0
    if kind == "test" and tiers and not tctx.get("main_paid"):
        event = _n(tiers["fast"])
        dl = f" до {_dm(tctx['deadline'])}" if tctx.get("deadline") else ""
        parts.append({"code": "event", "label": f"бонус «тест → основне», якщо клієнт оплатить основне замовлення{dl}",
                      "amount": round(event)})
    mx = now + (bonus(gross, over_pct) - base) + event
    return {"now": round(now), "max": round(max(mx, now)), "parts": parts, "estimate": bool(prev.get("estimate")),
            "note": "Попередньо: остаточна сума — у ЗП за місяць (план і стандарт рахуються за весь місяць)."}, disc_add


def _test_checks(deal, paid, amount, received, tctx, tiers, show_money, today):
    out = []
    if amount > 0 and paid + 0.5 >= amount:
        out.append(_chk("pay", "done", "Тест-набір оплачено повністю", "Правило: тест-набір — лише 100% передоплата."))
    elif paid > 0:
        out.append(_chk("pay", "todo", f"Оплачено {_fmt(paid)} з {_fmt(amount)} ₴",
                        "Тест-набір відправляємо лише після 100% оплати.", "кнопка «Прийняти оплату»"))
    else:
        out.append(_chk("pay", "todo", "Чекаємо оплату тест-набору", "Правило: 100% передоплата; після оплати — відправка.",
                        "кнопка «Прийняти оплату»"))
    rdate = _date_of(received)
    if rdate:
        out.append(_chk("delivery", "done", f"Клієнт отримав набір {_dm(rdate)}", date=rdate))
    elif deal.ttn:
        out.append(_chk("delivery", "info", f"В дорозі: {deal.stage.name}", f"ТТН {deal.ttn}. Коли клієнт отримає — CRM сама поставить «Отримано»."))
    elif paid > 0:
        out.append(_chk("delivery", "todo", "Оплачено, ТТН ще немає", "Перевірте, що склад зібрав і відправив набір.",
                        "блок «Доставка і документи»"))
    if rdate:
        c_from, c_to = rdate + timedelta(days=2), rdate + timedelta(days=3)
        wrote = None
        if deal.contact_id:
            try:
                from apps.inbox.models import Message
                wrote = (Message.objects.filter(conversation__contact_id=deal.contact_id, direction="out", internal=False,
                                                created_at__date__gt=rdate).order_by("created_at").values_list("created_at", flat=True).first())
            except Exception:
                wrote = None
        if wrote:
            out.append(_chk("call", "done", f"Після отримання ви вже писали клієнту ({_dm(wrote)})",
                            "Дзвінок теж рахується. Далі — підвести до основного замовлення.", date=wrote))
        elif today < c_from:
            out.append(_chk("call", "info", f"{_dm(c_from)}–{_dm(c_to)}: напишіть або подзвоніть «Як вам зразок?»",
                            "Спитайте, чи вийшло нанести, що сподобалось, яка площа — і запропонуйте прорахунок.", date=c_from))
        else:
            out.append(_chk("call", "todo", "Час написати або подзвонити: «Як вам зразок? Вийшло нанести?»",
                            f"Набір отримано {_dm(rdate)}. Спитайте про враження і площу — і запропонуйте прорахунок основного.",
                            "чат клієнта / кнопка дзвінка", date=c_from))
    if tctx.get("main_paid"):
        out.append(_chk("event", "done", f"Основне замовлення оплачено {_dm(tctx['main_paid'])}",
                        "Бонус «тест → основне» — у ЗП місяця оплати (отримує відповідальний за основну угоду).",
                        date=tctx["main_paid"]))
    elif tctx.get("first") and tiers:
        dl = tctx["deadline"]
        left = (dl - today).days
        if left >= 0:
            title = (f"Основне замовлення до {_dm(dl)} → +{_fmt(tiers['fast'])} ₴" if show_money
                     else f"Основне замовлення до {_dm(dl)} — повний бонус відповідальному")
            hint = (f"Лишилось {left} дн. Пізніше — +{_fmt(tiers['slow'])} ₴; основне менше {_fmt(tiers['min_order'])} ₴ — "
                    f"+{_fmt(tiers['small'])} ₴." if show_money else f"Лишилось {left} дн.")
            out.append(_chk("event", "todo", title, hint, date=dl))
        else:
            title = (f"Строк повного бонусу минув {_dm(dl)}; основне зараз → +{_fmt(tiers['slow'])} ₴" if show_money
                     else f"Строк повного бонусу минув {_dm(dl)} — основне замовлення все одно варто оформити")
            out.append(_chk("event", "todo", title, "Не відпускайте клієнта: запропонуйте прорахунок по площі.", date=dl))
    elif tiers:
        out.append(_chk("event", "info", "Бонус «тест → основне» рахується від дати оплати тест-набору"))
    return out


def _delivery_check(items, amount):
    sums = {"thin": 0.0, "support": 0.0, "textured": 0.0, "paint": 0.0, "other": 0.0}
    for i in items:
        sums[_mat(i)] += _n(i.total)
    total = sum(sums.values()) or amount
    if total <= 0 or (sums["thin"] + sums["textured"] + sums["paint"]) <= 0:
        return None
    where = "памʼятка «Умови доставки» (швидкі відповіді)"
    if sums["paint"] / total >= THIN_SHARE_MIN:
        return _chk("delivery", "info", "Фарби (Primalex, Play&Clean, Balakryl) — доставка завжди платна",
                    "Не обіцяйте безкоштовну доставку на фарби.", where)
    if sums["textured"] > 0:
        need = FREE_TEXTURED_FROM - total
        if need <= 0:
            return _chk("delivery", "done", f"Доставка на відділення НП безкоштовна (фактурні — від {_fmt(FREE_TEXTURED_FROM)} ₴)",
                        "Скажіть клієнту — це аргумент замість знижки. Курʼєр — за тарифом НП.", where)
        return _chk("delivery", "todo", f"До безкоштовної доставки бракує {_fmt(need)} ₴ (фактурні штукатурки — від {_fmt(FREE_TEXTURED_FROM)} ₴)",
                    "Замість знижки запропонуйте добрати: ґрунт, захисне покриття, запас матеріалу.", where)
    share = (sums["thin"] + sums["support"]) / total
    if sums["thin"] > 0 and share >= THIN_SHARE_MIN:
        need = FREE_THIN_FROM - total
        if need <= 0:
            return _chk("delivery", "done", f"Доставка на відділення НП безкоштовна (тонкошарові — від {_fmt(FREE_THIN_FROM)} ₴)",
                        "Скажіть клієнту — це аргумент замість знижки. Курʼєр — за тарифом НП.", where)
        return _chk("delivery", "todo", f"До безкоштовної доставки бракує {_fmt(need)} ₴ (тонкошарові — від {_fmt(FREE_THIN_FROM)} ₴)",
                    "Замість знижки запропонуйте добрати: захисне покриття, запас матеріалу, інструмент.", where)
    if sums["thin"] > 0:
        return _chk("delivery", "info", f"Тонкошарових — {round(share * 100)}% замовлення",
                    f"Безкоштовна доставка діє, коли тонкошарові (з підкладкою) — від 70% замовлення і сума від {_fmt(FREE_THIN_FROM)} ₴.", where)
    return None


def _prepay_check(deal, items, paid, amount):
    pt = (deal.pay_type or "").lower()
    cod = any(x in pt for x in ("prepay_np", "наклад", "післяпл", "послеопл", "cod"))
    tinted = any(_is_tinted(i) for i in items)
    where = "памʼятка «Накладений платіж» (швидкі відповіді)"
    if tinted:
        req = amount * 0.5
        title = f"Тонований колір: передоплата 50% — {_fmt(req)} ₴, без повернення"
        hint = ("Або тонер у шприцах — клієнт тонує сам (попередьте: такий колір ми не архівуємо). "
                "Накладений платіж для тонованого — лише після 50%.")
    else:
        pct = 20 if amount <= 5000 else (15 if amount <= 15000 else 10)
        req = amount * pct / 100
        title = (f"Накладений платіж: передоплата {pct}% — {_fmt(req)} ₴" if cod
                 else f"Якщо клієнт попросить накладений платіж: передоплата {pct}% — {_fmt(req)} ₴")
        hint = ("Не менше вартості доставки туди й назад; решта — при отриманні на Новій Пошті. "
                "Накладений платіж — лише для нетонованого і лише якщо клієнт сам попросив.")
    if paid > 0 and paid + 0.5 >= req:
        return _chk("prepay", "done", f"Передоплату отримано: {_fmt(paid)} ₴", title + ". " + hint, where)
    return _chk("prepay", "todo" if (cod or tinted) else "info", title, hint, where)


def _main_checks(deal, items, paid, amount, received, disc_loss, show_money):
    out = []
    fully_paid = amount > 0 and paid + 0.5 >= amount
    if items and not fully_paid:
        gross = sum(_n(i.base_sum) for i in items)
        disc = max(0.0, gross - amount)
        if disc <= 0.5:
            out.append(_chk("discount", "done", "Без знижки — ваш заробіток з угоди максимальний" if show_money else "Без знижки"))
        else:
            pct = disc / gross * 100 if gross else 0.0
            thr = _discount_threshold()
            title = f"Знижка {pct:.0f}% ({_fmt(disc)} ₴)"
            if show_money and disc_loss >= 1:
                title += f" забирає у вас {_fmt(disc_loss)} ₴ заробітку"
            hint = (f"Вища за поріг {thr:g}% з Фінмоделі. " if pct > thr else "") + \
                "Замість знижки запропонуйте безкоштовну доставку від порогу, запас матеріалу або захисне покриття."
            out.append(_chk("discount", "warn" if pct > thr else "info", title, hint, "вкладка «Товари» → знижка на позиції"))
        dl = _delivery_check(items, amount)
        if dl:
            out.append(dl)
    if amount > 0 and not fully_paid:
        out.append(_prepay_check(deal, items, paid, amount))
    elif fully_paid:
        out.append(_chk("prepay", "done", "Оплачено повністю"))
    if not fully_paid:
        area = _n(deal.area_m2) > 0 or any(v for k, v in (deal.qualification or {}).items() if ("area" in str(k) or "площ" in str(k)) and v)
        rooms = deal.rooms.count()
        if rooms or area:
            out.append(_chk("area", "done", "Розрахунок по площі є" + (f" ({rooms} приміщ.)" if rooms else "")))
        else:
            out.append(_chk("area", "todo", "Порахуйте матеріал по приміщеннях",
                            "Прорахунок по площі — сильний аргумент і менше помилок з кількістю.", "вкладка «Товари» → «Приміщення»"))
    rdate = _date_of(received)
    rr = None
    try:
        from apps.reviews.models import ReviewRequest
        rr = ReviewRequest.objects.filter(deal=deal).order_by("-created_at").first()
    except Exception:
        rr = None
    if rr is not None:
        out.append(_chk("review", "done" if rr.status == "submitted" else "info", f"Відгук: {rr.get_status_display()}"))
    elif rdate:
        out.append(_chk("review", "todo", f"Клієнт отримав замовлення {_dm(rdate)} — попросіть відгук", "",
                        "кнопка «Попросити відгук» вгорі картки", date=rdate))
    elif fully_paid:
        out.append(_chk("review", "info", "Після отримання — попросіть відгук", "", "кнопка «Попросити відгук» вгорі картки"))
    if deal.contact_id:
        ps = None
        try:
            from apps.partners.models import PartnerStatus
            ps = PartnerStatus.objects.select_related("level").filter(contact_id=deal.contact_id).first()
        except Exception:
            ps = None
        if ps is not None and ps.is_active:
            out.append(_chk("partner", "info", f"Клієнт — партнер ({ps.level.name})",
                            "Знижку дає партнерська програма — окремо не додавайте.", "картка клієнта → «Партнер»"))
        elif "master" in (getattr(deal.contact, "kinds", None) or []):
            out.append(_chk("partner", "todo", "Клієнт — майстер: запропонуйте партнерську програму", "",
                            "картка клієнта → «Партнер»"))
    return out


def _touch_check(deal, kind):
    if deal.stage.is_won or deal.stage.is_lost:
        return None
    from apps.crm.models import Task
    q = Q(deal=deal)
    if deal.contact_id:
        q |= Q(contact_id=deal.contact_id)
    # дотик менеджера — не складські задачі («Відвантажити…», тонування): їх ставить автоматика складу
    t = (Task.objects.filter(q, status__in=["open", "in_progress"]).exclude(kind__in=["warehouse", "tinting"])
         .order_by(F("due_at").asc(nulls_last=True), "id").first())
    focus = "Тест-набір: не забути, проконтролювати клієнта, тримати у фокусі. " if kind == "test" else ""
    if t is None:
        return _chk("touch", "todo", "Немає наступного дотику", focus + "Поставте задачу-нагадування з датою.", "кнопка «+ Задача» вгорі картки")
    if t.due_at and t.due_at < timezone.now():
        return _chk("touch", "warn", f"Задача прострочена з {_dm(t.due_at)}: {t.title[:80]}", focus, "«Задачі»", date=t.due_at)
    when = timezone.localtime(t.due_at).strftime("%d.%m %H:%M") if t.due_at else "без дати"
    return _chk("touch", "done", f"Наступний дотик: {when} — {t.title[:80]}", focus, "«Задачі»", date=t.due_at)


def _plan_check(u, deal, pol, today, paid, amount):
    sc = engine.active_scheme(u, today)
    comps = list(sc.components.filter(active=True)) if sc else []
    p = _plan_out(u, today.strftime("%Y-%m"), comps, pol)
    if not p or not p.get("target"):
        return None
    rate = (f"Понад план ставка {p['over_pct']:g}% замість {p['to_pct']:g}% (при оцінці стандарту від {p['gate_pct']}%)."
            if p.get("over_pct") and p.get("over_pct") != p.get("to_pct") else "")
    if p["left"]:
        hint = rate
        rest = amount - paid
        if rest > 0.5:
            hint = (hint + " " if hint else "") + f"Ця угода — ще {_fmt(rest)} ₴ до плану, коли прийде оплата."
        return _chk("plan", "info", f"План місяця: {p['pct']}% — лишилось {_fmt(p['left'])} ₴", hint, "«Розвиток» → «Моя ЗП і KPI»")
    return _chk("plan", "done", f"План місяця виконано ({p['pct']}%)", rate, "«Розвиток» → «Моя ЗП і KPI»")


FOCUS = {
    "test": "Тест-набір: не забути, проконтролювати клієнта, тримати у фокусі. Мета — основне замовлення вчасно.",
    "main": "Основне замовлення: менше знижок, безкоштовна доставка від порогу замість знижки, передоплата за правилом, "
            "після отримання — відгук.",
    "other": "Тримайте угоду у фокусі: наступний дотик і оплата.",
}
KIND_LABEL = {"test": "Тест-набір", "main": "Основний продукт", "other": "Інша угода"}


class DealKpiView(APIView):
    """GET /api/payroll/deal-kpi/<deal_id>/ — заробіток відповідального і чек-лист угоди. Маржу не віддає нікому.
    Суми ₴ і ставки — лише самому відповідальному (і праву payroll.rates.view); інші, хто бачить угоду, — лише чек-лист."""
    permission_classes = [IsAuthenticated]

    def get(self, request, deal_id):
        from apps.crm.models import Deal
        u = request.user
        deal = Deal.objects.select_related("owner", "contact", "funnel", "stage").filter(pk=deal_id).first()
        if deal is None:
            return Response({"detail": "Угоду не знайдено"}, status=404)
        if not _can_view_deal(u, deal):
            return Response({"detail": "Немає доступу до цієї угоди"}, status=403)
        pol = engine.policy()
        today = timezone.localdate()
        kind = ("test" if deal.funnel_id in (pol["funnels"].get("test") or [])
                else "other" if deal.funnel_id in (pol["funnels"].get("diamond") or []) else "main")
        is_owner_view = bool(deal.owner_id) and deal.owner_id == u.id
        show_money = is_owner_view or _can(u, "payroll.rates.view")
        items = list(deal.items.select_related("product", "product__category"))
        paid = _n(deal.payments.filter(is_paid=True).aggregate(s=Sum("amount"))["s"])
        amount = _n(deal.amount)
        sc = engine.active_scheme(deal.owner, today) if deal.owner_id else None
        ev = next((c for c in sc.components.filter(active=True, kind="event_bonus")), None) if sc else None
        tiers = _tiers(ev.params) if ev else None
        tctx = _test_ctx(deal, pol, tiers or _tiers({})) if kind == "test" else {}
        earn, disc_loss = (None, 0.0)
        if show_money and sc:
            earn, disc_loss = _deal_earn(deal, sc, pol, items, kind, tctx, tiers)
        received = _received_at(deal)
        if kind == "test":
            checks = _test_checks(deal, paid, amount, received, tctx, tiers, show_money, today)
        elif kind == "main":
            checks = _main_checks(deal, items, paid, amount, received, disc_loss, show_money)
        else:
            checks = []
        tc = _touch_check(deal, kind)
        if tc:
            checks.append(tc)
        if is_owner_view:
            pc = _plan_check(u, deal, pol, today, paid, amount)
            if pc:
                checks.append(pc)
        return Response({"deal_id": deal.id, "kind": kind, "kind_label": KIND_LABEL[kind], "focus": FOCUS[kind],
                         "show_money": show_money, "is_owner_view": is_owner_view, "owner_name": _who(deal.owner),
                         "earn": earn, "no_scheme": bool(show_money and deal.owner_id and not sc), "checks": checks})
