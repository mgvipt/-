"""KPI складу — «стандарт складу» з 8 пунктів (рішення Олега 15.09.2026: «KPI складу ок, я затверджую»).

Тверда частина комірника: 5 000 за вихід (по табелю) + 3 000 «стандарт складу» × оцінка місяця (пропорція 5/8 : 3/8).
Оцінку ставить керівник (Налаштування → Ставки співробітників → «Розрахунок за місяць»). CRM лише ПІДКАЗУЄ:
пункти 1, 4, 5, 6 рахує з даних складу, пункти 2, 3, 7, 8 відмічає керівник (поки не знято — «так»).
Кожен пункт = рівна частка оцінки. engine._c_standard рахує як і раніше: максимум × оцінка.

Що тут:
- WH_STANDARD_CRITERIA — 8 пунктів (params.criteria компонента «standard»); копія для екрана — PayRates.tsx WH_STD_CRITERIA;
- suggest_wh_standard(user, period, comp) — підказка по пунктах (ЛИШЕ читання: WarehouseJob, WarehousePhoto, WorkDay,
  StockDocument, IncomingDoc, WarehouseError; ~12 запитів незалежно від кількості днів);
- standard_plain / standard_rules — текст для «Моя ЗП» і «Як виконати план» (my_views);
- WhKpiView — GET підказка (payroll.rates.view), POST оцінка місяця + позначки пунктів (payroll.rates.edit, з PayRateLog).
  Маршрут додається в urls.py окремо (див. README пакета whkpi): path("wh-kpi/", WhKpiView.as_view()).
"""
import copy
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SHIP_CUTOFF = time(14, 0)   # оплачено (задача «Відвантажити» стала в чергу) до 14:00 → відправити того ж дня
DAY_END = time(18, 0)       # «кінець дня» складу для черги: Нова Пошта забирає до 17–18
AUTO_KEYS = ("ship_same_day", "weight_photo", "queue_clean", "receipt_same_day")
PICKING_KINDS = ("wrong_material", "wrong_tint", "wrong_qty")

WH_STANDARD_CRITERIA = [
    {"key": "ship_same_day", "title": "Відвантаження вчасно: оплачено до 14:00 — відправлено того ж дня",
     "how_measured": "auto", "target": "не менше 95% замовлень", "target_pct": 95},
    {"key": "no_picking_errors", "title": "Нуль помилок комплектації (не той товар / колір / кількість)",
     "how_measured": "manual", "target": "0 підтверджених помилок; кожна знижує стандарт; утримання 50% — окремо, як і було"},
    {"key": "no_damage", "title": "Нуль пошкоджень у дорозі через пакування (скарги / повернення «розбилось / протекло»)",
     "how_measured": "manual", "target": "0 випадків"},
    {"key": "weight_photo", "title": "Вага і фото посилки в CRM у кожного відвантаження",
     "how_measured": "auto", "target": "100% відвантажень", "target_pct": 100},
    {"key": "queue_clean", "title": "Черга порожня в кінці дня: задачі «Відвантажити» не старші доби",
     "how_measured": "auto", "target": "щодня — не менше 95% робочих днів", "target_pct": 95},
    {"key": "receipt_same_day", "title": "Прихід — у день надходження: накладна оприбуткована, собівартість є",
     "how_measured": "auto", "target": "не менше 95% накладних того ж дня; собівартість — у кожному рядку", "target_pct": 95},
    {"key": "stock_accuracy", "title": "Точність залишків: розбіжність при перерахунку полиці ≤ 1%; раз на тиждень вибіркова перевірка",
     "how_measured": "manual", "target": "розбіжність ≤ 1%, перевірка щотижня"},
    {"key": "order_timesheet", "title": "Порядок і табель: без запізнень і прогулів, фото порядку на складі раз на тиждень",
     "how_measured": "manual", "target": "0 запізнень і прогулів, фото щотижня"},
]
_DEFAULT = {c["key"]: c for c in WH_STANDARD_CRITERIA}

# Простими словами для «Як виконати план» (сторінка «Розвиток») — без мети: мета береться з пункту схеми.
PLAIN = {
    "ship_same_day": "Оплачено до 14:00 — відправити того ж дня. CRM бачить сама: коли задача «Відвантажити» стала "
                     "в чергу (це момент оплати) і коли ви натиснули «Відправлено».",
    "no_picking_errors": "Без помилок комплектації: той товар, той колір, та кількість. Кожна підтверджена помилка "
                         "знижує оцінку; утримання 50% суми угоди — окремо, як і було.",
    "no_damage": "Пакувати так, щоб у дорозі нічого не розбилось і не протекло. Скарга чи повернення через пакування "
                 "знижує оцінку.",
    "weight_photo": "У кожного відвантаження — вага посилки (місця в ТТН) і фото «Посилка» в задачі. "
                    "Самовивіз без ТТН — лише фото.",
    "queue_clean": "У кінці робочого дня в черзі немає задач «Відвантажити», які стоять понад добу. "
                   "CRM перевіряє кожен день вашого табеля о 18:00.",
    "receipt_same_day": "Товар прийшов — прихід оприбутковано того ж дня, у кожному рядку є собівартість "
                        "(накладні з пошти — за днем, коли лист потрапив у CRM).",
    "stock_accuracy": "Раз на тиждень — вибірковий перерахунок полиці; розбіжність із CRM не більше 1%.",
    "order_timesheet": "Без запізнень і прогулів; раз на тиждень — фото порядку на складі (керівнику).",
}
WHERE = [
    "«Відвантаження» — черга і ваші задачі: взяти задачу, фото «Відерця» і «Посилка», кнопка «Відправлено».",
    "Картка угоди → «Доставка НП»: місця і вага посилки в ТТН.",
    "«Складський облік» → прихід; «Фінанси → Вхідні накладні» — накладні з пошти (якщо є доступ): "
    "оприбуткувати в день надходження, перевірити собівартість у кожному рядку.",
    "«Складський облік» → інвентаризація: вибірковий перерахунок полиці раз на тиждень.",
    "«Відвантаження» → «Почати день» / «Завершити день» — з цього CRM сама заповнює табель.",
]


def criteria(comp=None):
    """(пункти, джерело): зі схеми (params.criteria), інакше — 8 пунктів складу. «auto» лишається лише для пунктів,
    які CRM вміє виміряти (AUTO_KEYS); решта — «відмічає керівник». target_pct — мета у % для авто-пунктів."""
    crit = engine.standard_criteria(comp) if comp is not None else []
    src = "scheme" if crit else "default"
    if not crit:
        crit = copy.deepcopy(WH_STANDARD_CRITERIA)
    out = []
    for c in crit:
        c = dict(c)
        if c.get("how_measured") == "auto" and c.get("key") not in AUTO_KEYS:
            c["how_measured"] = "manual"
        try:
            c["target_pct"] = float(c.get("target_pct", _DEFAULT.get(c.get("key"), {}).get("target_pct", 95)))
        except (TypeError, ValueError):
            c["target_pct"] = 95.0
        out.append(c)
    return out, src


# ─────────────────────────── дрібні помічники ───────────────────────────

def _aware(d, t):
    return timezone.make_aware(datetime.combine(d, t))


def _ld(dt):
    return timezone.localtime(dt).date() if dt else None


def _dmt(dt):
    return timezone.localtime(dt).strftime("%d.%m %H:%M") if dt else "—"


def _pct(ok, total):
    return round(ok * 100.0 / total, 1) if total else None


def _seats_kg(npd):
    """Вага посилки з форми «Доставка НП» (місця ТТН: [{kg, …}])."""
    try:
        return sum(float((s or {}).get("kg") or 0) for s in ((npd or {}).get("seats") or []))
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _auto(ok, total, target, empty_text, details, extra=None):
    """Результат авто-пункту: value — % виконання; pass — None, якщо даних немає (тоді оцінку не знижуємо)."""
    v = _pct(ok, total)
    return {"value": v, "value_text": f"{ok} з {total} — {round(v)}%" if total else empty_text,
            "pass": None if v is None else v >= target, "details": (extra or []) + details}


# ─────────────────────────── підказка CRM ───────────────────────────

def suggest_wh_standard(user, period, comp=None, today=None):
    """Підказка CRM по стандарту складу за місяць. ЛИШЕ читання, ~12 запитів.

    1 «оплачено до 14:00 → відправлено того ж дня»: задачі «Відвантажити», що стали в чергу (CRM ставить задачу
      в момент оплати — стадія «Оплату отримано») до 14:00 у робочий день людини; виконано, якщо «Відправлено»
      натиснуто того ж календарного дня. Чиє: хто взяв задачу; не взяту — хто був на зміні.
    4 «вага і фото»: відвантаження людини — є фото «Посилка» і вага (місця ТТН або вага замовлення);
      без ТТН (самовивіз) — лише фото.
    5 «черга»: кожен робочий день людини о 18:00 — чи немає задач «Відвантажити», створених раніше, ніж о 18:00
      попереднього дня, і досі не відправлених.
    6 «прихід»: приходи місяця — накладна з пошти оприбуткована того ж дня, коли лист потрапив у CRM;
      у кожному рядку є собівартість. Пункт спільний для складу (прихід оформлює той, хто має доступ).
    Дозамовлення, що їдуть у коробці основного замовлення, і скасовані задачі не рахуються (часу скасування CRM не зберігає).
    2, 3, 7, 8 — «так», поки керівник не зняв позначку (params.items[period]); CRM показує лише довідку.
    Оцінка = виконані пункти ÷ усі пункти; авто-пункт без даних оцінку не знижує. Рахуємо лише завершені дні."""
    from apps.finance.models import WorkDay
    from apps.integrations.models import IncomingDoc
    from apps.warehouse.models import StockDocument, WarehouseError, WarehouseJob, WarehousePhoto

    today = today or timezone.localdate()
    d1, d2 = engine.period_bounds(period)
    last = min(d2, today - timedelta(days=1))
    crit, src = criteria(comp)
    tgt = {c["key"]: c["target_pct"] for c in crit}
    items_all = ((comp.params or {}).get("items") or {}) if comp is not None else {}
    stored = items_all.get(period) if isinstance(items_all, dict) else None
    stored = stored if isinstance(stored, dict) else {}
    res, hints = {}, {}
    workdays, wd_src = 0, "табель"
    if last >= d1:
        start, end = _aware(d1, time(0)), _aware(last, time(23, 59, 59))
        jobs = list(WarehouseJob.objects.filter(is_shipment=True, created_at__lte=end).exclude(status="cancelled")
                    .filter(Q(shipped_at__isnull=True) | Q(shipped_at__gte=start - timedelta(days=1)))
                    .select_related("deal")
                    .defer("done_snapshot", "deal__ref_photos", "deal__kp_history", "deal__qualification",
                           "deal__card_fields", "deal__meta_attribution"))
        # дозамовлення їде в коробці основної угоди (у якої є своя задача) — окремо не рахуємо
        parents = {j.deal.parent_deal_id for j in jobs if j.deal.parent_deal_id}
        with_job = set(WarehouseJob.objects.filter(deal_id__in=parents).exclude(status="cancelled")
                       .values_list("deal_id", flat=True)) if parents else set()
        jobs = [j for j in jobs if not j.deal.parent_deal_id or j.deal.parent_deal_id not in with_job]

        # табель: хто в які дні був на зміні (WorkDay ставиться сам кнопкою «Почати день»)
        uids = {user.id} | {j.assignee_id for j in jobs if j.assignee_id}
        worked = defaultdict(set)
        for uid, dd in (WorkDay.objects.filter(user_id__in=uids, date__gte=d1, date__lte=last, status__in=["worked", "overtime"])
                        .values_list("user_id", "date")):
            worked[uid].add(dd)
        if not worked[user.id]:
            worked[user.id] = {_ld(j.shipped_at) for j in jobs
                               if j.assignee_id == user.id and j.shipped_at and d1 <= _ld(j.shipped_at) <= last}
            wd_src = "табель порожній — узято дні відвантажень"
        mine = worked[user.id]
        workdays = len(mine)

        def on_me(j, day):
            """Чия задача того дня: взята людиною; не взята; або взята кимось, хто того дня не працював."""
            if day not in mine:
                return False
            a = j.assignee_id
            return a is None or a == user.id or day not in worked[a]

        # 1. оплачено до 14:00 → відправлено того ж дня
        ok = tot = 0
        fails = []
        for j in jobs:
            q = timezone.localtime(j.created_at)
            if not (d1 <= q.date() <= last) or q.time() >= SHIP_CUTOFF or not on_me(j, q.date()):
                continue
            tot += 1
            if j.shipped_at and _ld(j.shipped_at) == q.date():
                ok += 1
            else:
                fails.append(f"угода #{j.deal_id}: у черзі з {q:%d.%m %H:%M}, "
                             + (f"відправлено {_dmt(j.shipped_at)}" if j.shipped_at else "ще не відправлено"))
        res["ship_same_day"] = _auto(ok, tot, tgt.get("ship_same_day", 95), "замовлень до 14:00 у ваші зміни не було", fails)

        # 4. вага і фото посилки
        shipped = [j for j in jobs if j.assignee_id == user.id and j.status == "shipped" and j.shipped_at
                   and d1 <= _ld(j.shipped_at) <= last]
        photos = set(WarehousePhoto.objects.filter(job_id__in=[j.id for j in shipped], kind="parcel")
                     .values_list("job_id", flat=True)) if shipped else set()
        ok, fails, no_ttn = 0, [], 0
        for j in shipped:
            kg = _seats_kg(j.deal.np_data)
            need_w = bool((j.deal.ttn or "").strip()) or kg > 0
            no_ttn += 0 if need_w else 1
            w_ok = float(j.shipped_weight_kg or 0) > 0 or kg > 0
            if j.id in photos and (w_ok or not need_w):
                ok += 1
            else:
                miss = ([] if j.id in photos else ["фото посилки"]) + ([] if (w_ok or not need_w) else ["ваги"])
                fails.append(f"угода #{j.deal_id} (відправлено {_dmt(j.shipped_at)}): немає {' і '.join(miss)}")
        extra = [f"без ТТН (самовивіз / інша доставка): {no_ttn} — для них перевірено лише фото"] if no_ttn else []
        res["weight_photo"] = _auto(ok, len(shipped), tgt.get("weight_photo", 100), "ваших відвантажень не було", fails, extra)

        # 5. черга в кінці дня: немає задач, старших за добу
        ok, fails, stuck = 0, [], {}
        days = sorted(d for d in mine if d1 <= d <= last)
        for day in days:
            cut = _aware(day, DAY_END)
            old = cut - timedelta(days=1)
            late = [j for j in jobs if j.created_at <= old and (j.shipped_at is None or j.shipped_at > cut) and on_me(j, day)]
            if not late:
                ok += 1
                continue
            for j in late:
                if (cut - j.created_at).days >= 7:
                    stuck[j.id] = j
            fails.append(f"{day:%d.%m}: задач старших за добу — {len(late)} (угоди "
                         + ", ".join(f"#{j.deal_id}" for j in late[:6]) + ("…" if len(late) > 6 else "") + ")")
        extra = [f"угода #{j.deal_id}: задача «Відвантажити» стоїть з {_dmt(j.created_at)} — якщо відвантаження не потрібне, "
                 "скасуйте задачу, інакше вона щодня псує цей пункт" for j in stuck.values()]
        res["queue_clean"] = _auto(ok, len(days), tgt.get("queue_clean", 95), "робочих днів у табелі немає", fails, extra)

        # 6. прихід у день надходження, собівартість є (спільний пункт складу)
        docs = list(StockDocument.objects.filter(kind="in", created_at__gte=start, created_at__lte=end)
                    .select_related("author").prefetch_related("items"))
        inc = {i.id: i for i in IncomingDoc.objects.filter(id__in=[d.source_invoice_doc for d in docs if d.source_invoice_doc])}
        pending = list(IncomingDoc.objects.filter(doc_type="supplier", status="draft", created_at__gte=start, created_at__lte=end))
        known = same = cost_ok = 0
        fails, authors = [], Counter()
        for d in docs:
            authors[(d.author.get_full_name() or d.author.username) if d.author_id else "—"] += 1
            rows = list(d.items.all())
            if d.posted and rows and all((r.price or 0) > 0 for r in rows):
                cost_ok += 1
            else:
                fails.append(f"прихід #{d.id} від {_dmt(d.created_at)}: "
                             + ("чернетка — не проведено" if not d.posted else "немає собівартості в рядку"))
            i = inc.get(d.source_invoice_doc) if d.source_invoice_doc else None
            if i:
                known += 1
                arr = i.received_at or i.created_at
                if d.posted and _ld(d.created_at) == _ld(arr):
                    same += 1
                else:
                    fails.append(f"накладна з пошти від {_dmt(arr)} оприбуткована {_dmt(d.created_at)}")
        for i in pending:
            known += 1
            fails.append(f"накладна з пошти від {_dmt(i.received_at or i.created_at)} ще не оприбуткована")
        v = _pct(same, known)
        t6 = tgt.get("receipt_same_day", 95)
        info = []
        if docs:
            info.append("оприбутковує: " + ", ".join(f"{n} ({k} з {len(docs)})" for n, k in authors.most_common())
                        + " — пункт спільний для складу")
        if len(docs) - (known - len(pending)):
            info.append(f"приходів без накладної з пошти: {len(docs) - (known - len(pending))} — дня надходження CRM не знає, "
                        "перевірено лише собівартість")
        if not docs and not pending:
            res["receipt_same_day"] = {"value": None, "value_text": "приходів за місяць не було", "pass": None, "details": []}
        else:
            res["receipt_same_day"] = {
                "value": v if v is not None else _pct(cost_ok, len(docs)),
                "value_text": (f"того ж дня {same} з {known} — {round(v)}%; " if known else "")
                              + f"собівартість є в {cost_ok} з {len(docs)}",
                "pass": (v is None or v >= t6) and cost_ok == len(docs), "details": info + fails}

        # довідка для пунктів керівника
        errs = list(WarehouseError.objects.filter(blamed_user=user, created_at__gte=start, created_at__lte=end)
                    .values_list("kind", "status"))
        pick_c = sum(1 for k, s in errs if k in PICKING_KINDS and s == "confirmed")
        pick_s = sum(1 for k, s in errs if k in PICKING_KINDS and s == "suggested")
        dmg_c = sum(1 for k, s in errs if k == "damaged" and s == "confirmed")
        inv = sorted({_ld(x) for x in StockDocument.objects.filter(kind="inv", created_at__gte=start, created_at__lte=end)
                      .values_list("created_at", flat=True)})
        absent = WorkDay.objects.filter(user=user, date__gte=d1, date__lte=last, status="absent").count()
        clean = WarehousePhoto.objects.filter(employee=user, kind="cleanliness", uploaded_at__gte=start, uploaded_at__lte=end).count()
        hints = {
            "no_picking_errors": f"У CRM за місяць: підтверджених помилок комплектації — {pick_c}"
                                 + (f", ще на розгляді — {pick_s}" if pick_s else "") + ".",
            "no_damage": f"У CRM за місяць: підтверджених пошкоджень — {dmg_c}. Скарги клієнтів на пакування CRM окремо "
                         "не рахує — зніміть галочку, якщо були.",
            "stock_accuracy": (f"Перерахунків (інвентаризацій) у CRM за місяць: {len(inv)} ("
                               + ", ".join(f"{x:%d.%m}" for x in inv) + ")" if inv
                               else "Перерахунків (інвентаризацій) у CRM за місяць немає")
                              + ". Розбіжність у % CRM поки не рахує.",
            "order_timesheet": f"Табель: прогулів — {absent}; фото «Чистота» в CRM — {clean}. Запізнень CRM не рахує: "
                               "графіка змін у CRM немає.",
        }
    points = []
    for n, c in enumerate(crit, 1):
        base = {"n": n, "key": c["key"], "title": c["title"], "how_measured": c["how_measured"],
                "target": c.get("target") or "", "target_pct": c["target_pct"] if c["how_measured"] == "auto" else None}
        if c["how_measured"] == "auto":
            r = res.get(c["key"]) or {"value": None, "value_text": "днів для перевірки ще немає", "pass": None, "details": []}
            points.append({**base, **r, "hint": "", "mark": r["pass"] is not False, "marked": False})
        else:
            m = stored.get(c["key"])
            points.append({**base, "value": None, "value_text": "", "pass": None, "details": [],
                           "hint": hints.get(c["key"], ""), "mark": m is not False, "marked": m is not None})
    good = sum(1 for p in points if p["mark"])
    score = round(good / len(points), 4) if points else 1.0
    return {"period": period, "user_id": user.id, "user_name": user.get_full_name() or user.username,
            "from": d1.isoformat(), "to": last.isoformat() if last >= d1 else None, "partial": last < d2,
            "criteria_source": src, "workdays": workdays, "workdays_source": wd_src,
            "points": points, "good": good, "suggested_score": score, "suggested_pct": int(score * 100 + 0.5),   # як в екрані (Math.round): 5 з 8 → 63%
            "rule": f"Кожен пункт — 1/{len(points)} оцінки. Пункти CRM: «ні» — мінус пункт, немає даних — не знижує. "
                    "Пункти керівника — «так», поки галочку не знято."}


# ─────────────────────────── тексти для «Моя ЗП» і «Як виконати план» ───────────────────────────

def standard_plain(comp):
    """Одне речення для «Моя ЗП → схема простими словами»."""
    crit, _src = criteria(comp)
    n = len(crit)
    auto = sum(1 for c in crit if c["how_measured"] == "auto")
    mx = engine._n((comp.params or {}).get("max"))
    return (f"Стандарт роботи: до {mx} ₴ × оцінка місяця за {n} пунктами (кожен пункт — 1/{n}; "
            f"{auto} CRM рахує сама, {n - auto} відмічає керівник). Пункти — у «Як виконати план».")


def standard_rules(comp):
    """Блок «Стандарт роботи» у «Як виконати план» для стандарту з пунктами: пункти простими словами + куди дивитись."""
    crit, _src = criteria(comp)
    n = len(crit)
    need = []
    for i, c in enumerate(crit, 1):
        what = PLAIN.get(c["key"]) or (c["title"].rstrip(".") + ".")
        who = "CRM рахує сама" if c["how_measured"] == "auto" else "Відмічає керівник"
        tgt = f" Мета: {c['target']}." if c.get("target") else ""
        need.append(f"{i}. {c['title']}. {what}{tgt} {who}.")
    mx = engine._n((comp.params or {}).get("max"))
    need.append(f"Оцінка місяця = частка виконаних пунктів (кожен — 1/{n}); 100% — повна сума до {mx} ₴. "
                "Поки оцінки немає, у розрахунку стоїть 100%.")
    return {"kind": "standard", "title": comp.title or "Стандарт роботи", "need": need,
            "where": WHERE if any(c["key"] in _DEFAULT for c in crit) else []}


# ─────────────────────────── API ───────────────────────────

class WhKpiView(APIView):
    """GET ?scheme=ID&period=YYYY-MM — підказка CRM по стандарту (право payroll.rates.view).
    POST {component, period, score?, items{key: bool}} — оцінка місяця і позначки пунктів (payroll.rates.edit);
    запис — лише params компонента (як ComponentMarkView) + рядок в «Історії змін» (PayRateLog, action=mark)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import PayScheme
        from .views import _can, _deny
        if not _can(request.user, "payroll.rates.view"):
            return _deny()
        period = (request.query_params.get("period") or timezone.localdate().strftime("%Y-%m"))[:7]
        if not PERIOD_RE.match(period):
            return Response({"detail": "Період — у форматі YYYY-MM"}, status=400)
        sid = request.query_params.get("scheme") or ""
        sc = PayScheme.objects.filter(pk=sid).select_related("user").first() if str(sid).isdigit() else None
        if not sc or not sc.user_id:
            return Response({"detail": "Схему співробітника не знайдено"}, status=404)
        comp = sc.components.filter(kind="standard", active=True).order_by("order", "id").first()
        return Response(suggest_wh_standard(sc.user, period, comp))

    def post(self, request):
        from .models import PayComponent, PayRateLog
        from .views import _can, _comp_json, _deny
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права змінювати ставки")
        cid = request.data.get("component")
        c = PayComponent.objects.filter(pk=cid, kind="standard").select_related("scheme").first() if str(cid or "").isdigit() else None
        period = str(request.data.get("period") or "")[:7]
        if not c or not PERIOD_RE.match(period):
            return Response({"detail": "Невірні дані"}, status=400)
        raw = request.data.get("items") or {}
        if not isinstance(raw, dict):
            return Response({"detail": "items — обʼєкт {пункт: так/ні}"}, status=400)
        crit = engine.standard_criteria(c)
        keys = {x["key"] for x in crit}
        items = {k: bool(v) for k, v in raw.items() if k in keys}
        before = copy.deepcopy(c.params or {})
        p = copy.deepcopy(c.params or {})
        p["items"] = {**(p.get("items") if isinstance(p.get("items"), dict) else {}), period: items}
        score = None
        if request.data.get("score") is not None:
            try:
                score = max(0.0, min(1.0, float(request.data.get("score"))))
            except (TypeError, ValueError):
                return Response({"detail": "Оцінка — число від 0 до 1"}, status=400)
            p["scores"] = {**(p.get("scores") if isinstance(p.get("scores"), dict) else {}), period: score}
        c.params = p
        c.save(update_fields=["params"])
        miss = [str(i + 1) for i, x in enumerate(crit) if items.get(x["key"]) is False]
        note = f"Стандарт · {period}: " + (f"оцінка {round(score * 100)}%" if score is not None else "позначки пунктів")
        note += f"; не виконано пункти {', '.join(miss)}" if miss else "; усі пункти виконано"
        PayRateLog.objects.create(scheme=c.scheme, action="mark", before={"params": before}, after={"params": p},
                                  user=request.user, note=note[:255])
        return Response(_comp_json(c))
