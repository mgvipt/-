"""Бали за НОВИМИ правилами (Розвиток v2, 16.09.2026). Тут лише ЧИТАННЯ даних; запис — apply() через xp.award (ідемпотентно).

За що бали (людина це контролює, і це гроші компанії):
  test_main    «Тест-набір → основне»: бал = бонус ₴ за ВАШОЮ ставкою ÷ 10 (300 ₴ → 30, 200 ₴ → 20, 100 ₴ → 10).
               Умова рівно як у ЗП (engine._c_event): перше оплачене основне замовлення клієнта після оплаченого
               тест-набору; бал — відповідальному за основну угоду, у місяці першої оплати основного.
  no_discount  Основне замовлення від мінімуму бонусу (3 000 ₴) оплачено без знижки на позиціях: 10 балів.
  review       Клієнт залишив відгук по вашій угоді: 20 балів.
  review_ask   Ви вручну попросили відгук (кнопка «Попросити відгук»): 5 балів, раз на угоду.
  quality      Розбір дзвінка (і випадкової вибірки чатів, якщо її увімкнено): (бал − 40) × 0,5, не менше 0,
               + 3 за навичку від 80 + 20 за розбір від 75 — тому, хто говорив (xp.award_for_analysis).
               Слабкий дзвінок балів не дає — бали за якість, а не за кількість дзвінків.
Чого НЕ даємо: за сам факт виграної угоди, за кількість дій, за «швидку першу відповідь» (у ~9 з 10 чатів першою
відповідає Юля — така метрика була б нечесною), за розбір чату «вручну» (можна вибрати лише вдалі).
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from apps.payroll import engine

TIER_DIV = 10
NO_DISCOUNT_XP = 10
REVIEW_XP = 20
REVIEW_ASK_XP = 5
DEFAULT_TIERS = {"fast_days": 30, "min_order": 3000, "fast": 300, "slow": 200, "small": 100}
NEW_KINDS = ("test_main", "no_discount", "review", "review_ask", "quality")

KIND_LABELS = {
    "test_main": "Тест-набір → основне",
    "no_discount": "Основне без знижки",
    "review": "Відгук клієнта",
    "review_ask": "Попросив відгук",
    "quality": "Розбір розмови",
    "bonus": "Інше",
}
KIND_RULES = {
    "test_main": "бонус ₴ «тест → основне» за вашою ставкою ÷ 10: вчасно 30, пізніше 20, основне менше 3 000 ₴ — 10",
    "no_discount": f"основне від 3 000 ₴ оплачено без знижки на позиціях — {NO_DISCOUNT_XP} балів",
    "review": f"клієнт залишив відгук по вашій угоді — {REVIEW_XP} балів",
    "review_ask": f"ви вручну попросили відгук — {REVIEW_ASK_XP} балів (раз на угоду)",
    "quality": "(бал розбору − 40) × 0,5 + 3 за кожну навичку від 80 + 20 за розбір від 75; розбір до 40 — 0",
}


def _when(d):
    """Дата події → час 12:00 за Києвом (щоб бал точно ліг у свій місяць)."""
    return timezone.make_aware(datetime.combine(d, time(12, 0)))


def _ev(uid, kind, xp, ref_type, ref_id, d, meta):
    return {"manager_id": uid, "kind": kind, "xp": int(xp), "ref_type": ref_type, "ref_id": str(ref_id),
            "date": d, "meta": meta}


def tiers_for(uid, on, cache):
    """Ступені бонусу «тест → основне» зі СВОЄЇ ставки людини (як у ЗП); немає компонента — стандартні 300/200/100."""
    if uid in cache:
        return cache[uid]
    t = dict(DEFAULT_TIERS)
    try:
        from apps.accounts.models import User
        u = User.objects.filter(pk=uid).first()
        sc = engine.active_scheme(u, on) if u else None
        c = sc.components.filter(active=True, kind="event_bonus").first() if sc else None
        if c is not None:
            t.update((c.params or {}).get("tiers") or {})
    except Exception:
        pass
    cache[uid] = t
    return t


def collect(since, until, user_ids=None):
    """Події нових правил (крім quality — її дає сигнал розбору) з датою події since..until. Лише читання."""
    from apps.crm.models import Deal
    pol = engine.policy()
    fp = {r["deal_id"]: r for r in engine._first_pay()}
    ids = [i for i, r in fp.items() if since <= r["first"] <= until]
    mains = Deal.objects.filter(engine.kind_q("main", pol), owner__isnull=False, id__in=ids)  # 17.09: + воронки сайтів
    if user_ids is not None:
        mains = mains.filter(owner_id__in=list(user_ids))
    mains = list(mains.prefetch_related("items__product"))
    contacts = {d.contact_id for d in mains if d.contact_id}
    tests_by, mains_by = defaultdict(list), defaultdict(list)
    for did, cid, fid in Deal.objects.filter(engine.kind_q("test", pol) | engine.kind_q("main", pol), contact_id__in=contacts).values_list("id", "contact_id", "funnel_id"):
        if did in fp:
            (tests_by if engine.deal_kind(did, fid, pol) == "test" else mains_by)[cid].append((fp[did]["first"], did))
    out, tcache = [], {}
    for d in mains:
        first_main = fp[d.id]["first"]
        t = tiers_for(d.owner_id, first_main, tcache)
        if d.contact_id:
            tests = [f for f, _x in tests_by[d.contact_id] if f <= first_main]
            if tests:
                t0 = min(tests)
                earlier = [x for f, x in mains_by[d.contact_id] if x != d.id and t0 <= f < first_main]
                if not earlier:
                    days = (first_main - t0).days
                    order = float(fp[d.id]["total"] or d.amount or 0)
                    b = t["small"] if order < t["min_order"] else (t["fast"] if days <= t["fast_days"] else t["slow"])
                    out.append(_ev(d.owner_id, "test_main", round(float(b) / TIER_DIV), "deal", d.id, first_main,
                                   {"days": days, "bonus": float(b), "deal": d.id}))
        items = list(d.items.all())
        amount = float(d.amount or 0)
        if items and amount >= float(t["min_order"]):
            disc = sum(float(i.discount_sum or 0) for i in items)
            if disc <= 0.5:
                out.append(_ev(d.owner_id, "no_discount", NO_DISCOUNT_XP, "deal", d.id, first_main,
                               {"amount": round(amount), "deal": d.id}))
    out += _reviews(since, until, user_ids)
    return out


def _reviews(since, until, user_ids):
    from apps.reviews.models import ReviewRequest
    out = []
    lo, hi = _when(since) - timedelta(hours=12), _when(until) + timedelta(hours=12)
    got = (ReviewRequest.objects.filter(is_test=False, status="submitted", deal__isnull=False, deal__owner__isnull=False,
                                        submitted_at__gte=lo, submitted_at__lt=hi).select_related("deal"))
    for r in got:
        if user_ids is not None and r.deal.owner_id not in user_ids:
            continue
        d = timezone.localtime(r.submitted_at).date()
        out.append(_ev(r.deal.owner_id, "review", REVIEW_XP, "review", r.id, d, {"deal": r.deal_id}))
    asked = (ReviewRequest.objects.filter(is_test=False, kind="manual", created_by__isnull=False, deal__isnull=False,
                                          created_at__gte=lo, created_at__lt=hi).order_by("created_at"))
    seen = set()
    for r in asked:
        if r.deal_id in seen or (user_ids is not None and r.created_by_id not in user_ids):
            continue
        seen.add(r.deal_id)
        d = timezone.localtime(r.created_at).date()
        out.append(_ev(r.created_by_id, "review_ask", REVIEW_ASK_XP, "reviewask", r.deal_id, d, {"deal": r.deal_id}))
    return [e for e in out if since <= e["date"] <= until]


def quality_pending(since, until):
    """Розбори, які мали б дати бали, але їх ще немає (напр., розбір створено до встановлення пакета)."""
    from apps.crm.models import DialogAnalysis
    from .models import XPEvent
    done = set(XPEvent.objects.filter(kind="quality", ref_type="analysis").values_list("ref_id", flat=True))
    qs = DialogAnalysis.objects.filter(kind="call", manager__isnull=False,
                                       created_at__gte=_when(since) - timedelta(hours=12),
                                       created_at__lt=_when(until) + timedelta(hours=12))
    return [da for da in qs if str(da.id) not in done]


def speaker_of(call):
    """Хто говорив у дзвінку: оператор (call.manager) або власник внутрішнього номера (call.extension = User.extension,
    рівно одна активна людина). None — АТС не передала оператора (тоді розбір іде власнику угоди з позначкою owner)."""
    if call is None:
        return None
    if call.manager_id:
        return call.manager_id
    ext = (call.extension or "").strip()
    if ext.isdigit():
        from apps.accounts.models import User
        ids = list(User.objects.filter(extension=ext, is_active=True).values_list("id", flat=True)[:2])
        if len(ids) == 1:
            return ids[0]
    return None


def apply(events, live=False):
    """Записати події (ідемпотентно). live=False — лише порахувати, що було б записано."""
    from .models import XPEvent
    from .xp import award
    new, skip = [], 0
    for e in events:
        if XPEvent.objects.filter(kind=e["kind"], ref_type=e["ref_type"], ref_id=e["ref_id"]).exists():
            skip += 1
            continue
        new.append(e)
        if live:
            award(e["manager_id"], e["kind"], e["xp"], e["ref_type"], e["ref_id"], e["meta"], when=_when(e["date"]))
    return {"new": new, "skipped": skip}


def summarize(events):
    by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for e in events:
        r = by[e["manager_id"]][e["kind"]]
        r[0] += 1
        r[1] += e["xp"]
    return by


def month_points(uid, d1, d2):
    """Бали людини за календарний місяць по видах: [{kind, label, rule, count, xp}] і разом."""
    from .xp import live_events
    rows = (live_events().filter(manager_id=uid, created_at__date__gte=d1, created_at__date__lte=d2)
            .values("kind").annotate(n=Count("id"), s=Sum("xp")).order_by("-s"))
    out = [{"kind": r["kind"], "label": KIND_LABELS.get(r["kind"], r["kind"]), "rule": KIND_RULES.get(r["kind"], ""),
            "count": r["n"], "xp": int(r["s"] or 0)} for r in rows]
    return out, sum(r["xp"] for r in out)
