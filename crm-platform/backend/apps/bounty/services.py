"""Логіка біржі задач (14.09.2026).

Права:
  bounty.view   — бачити біржу і брати задачі. За замовчуванням є в УСІХ активних співробітників (рішення Олега:
                  біржу бачать і беруть усі); забрати в людини — «Заборонені права» → bounty.view.
  bounty.manage — прайс (додати / змінити / видалити / увімкнути), приймати будь-які задачі, підсумки всієї команди.
  Призначений у задачі «Хто приймає» приймає задачі лише цієї позиції. Свою задачу не приймає ніхто, крім власника.

Мʼяке правило стандарту: брати задачі — коли основний стандарт (Ставки → «Стандарт роботи», оцінку ставить власник
щомісяця) від 75%. Нижче — CRM попереджає і записує попередження в задачу, але НЕ блокує.

Фонд: стаття Фінмоделі з назвою «Біржа задач» (₴/міс). Значення > 0 — ліміт місяця (прийняте + взяте в роботу);
0 або статті немає — ліміт не діє, керівник бачить попередження. Статтю CRM сама НЕ створює.
"""
import re
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.utils import timezone

from .models import DEPARTMENT_LABELS, DEPARTMENTS, ClaimFile, TaskCategory, TaskClaim, TaskOffer

MIN_STANDARD = 0.75
FUND_NAME = "Біржа задач"
ACTIVE = ("taken", "submitted", "rework")
STATUS_LABELS = dict(TaskClaim.STATUS)
UNIT_LABELS = dict(TaskOffer.UNIT)
PROOF_LABELS = dict(TaskOffer.PROOF)
D0 = Decimal("0")
D1 = Decimal("1")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_FILE = 10 * 1024 * 1024
MAX_FILES = 10


class BountyError(Exception):
    def __init__(self, detail, status=400, code="", extra=None):
        super().__init__(detail)
        self.detail, self.status, self.code, self.extra = detail, status, code, (extra or {})


# ─────────────────────────── дрібниці ───────────────────────────

def dec(v, default=None, lo=None, hi=None, field="Число"):
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    try:
        d = Decimal(str(v).replace(",", ".").replace(" ", "").replace(" ", ""))
    except (InvalidOperation, ValueError):
        raise BountyError(f"{field}: потрібне число")
    if not d.is_finite():
        raise BountyError(f"{field}: потрібне число")
    if lo is not None and d < lo:
        raise BountyError(f"{field}: не менше {fmt(lo)}")
    if hi is not None and d > hi:
        raise BountyError(f"{field}: не більше {fmt(hi)}")
    return d


def to_int(v, field, lo=0, hi=100000):
    if v is None or v == "":
        return lo
    try:
        n = int(Decimal(str(v)))
    except (InvalidOperation, ValueError):
        raise BountyError(f"{field}: потрібне ціле число")
    if n < lo or n > hi:
        raise BountyError(f"{field}: від {lo} до {hi}")
    return n


def to_bool(v):
    return v in (True, 1, "1", "true", "True", "on", "yes")


def fmt(d):
    s = f"{Decimal(str(d or 0)):.2f}".rstrip("0").rstrip(".")
    return s or "0"


def money(d):
    return round(float(d or 0), 2)


def month_of(d=None):
    d = d or timezone.localdate()
    return f"{d.year:04d}-{d.month:02d}"


def next_month(p):
    y, m = int(p[:4]), int(p[5:7]) + 1
    if m > 12:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def prev_month(p):
    y, m = int(p[:4]), int(p[5:7]) - 1
    if m < 1:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def valid_period(p):
    return bool(p and PERIOD_RE.match(str(p)))


def who(u):
    return (u.get_full_name() or u.username) if u else ""


def _iso(v):
    return v.isoformat() if v else None


def unit_text(unit, unit_label, price):
    if unit == "pct":
        return f"{fmt(price)}% з оплат"
    if unit == "piece":
        return f"{fmt(price)} ₴ за {unit_label or 'штуку'}"
    if unit == "hour":
        return f"{fmt(price)} ₴ за годину"
    return f"{fmt(price)} ₴ за задачу"


def _ev(user, act, note=""):
    return {"at": timezone.now().isoformat(), "by": user.id if user else None, "by_name": who(user), "act": act,
            "note": (note or "")[:500]}


# ─────────────────────────── права ───────────────────────────

def _has(u, code):
    return bool(u and u.is_authenticated and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(code))))


def is_client(u):
    ak = getattr(type(u), "AccountKind", None)
    return bool(ak is not None and getattr(u, "account_kind", None) == getattr(ak, "CLIENT", object()))


def can_view(u):
    if not (u and u.is_authenticated and u.is_active):
        return False
    if u.is_superuser:
        return True
    if is_client(u):
        return False
    if "bounty.view" in (getattr(u, "denied_permissions", None) or []):
        return False
    return True  # за замовчуванням — усі активні співробітники


def can_manage(u):
    return _has(u, "bounty.manage")


def can_review(u, claim):
    if not (u and u.is_authenticated):
        return False
    if claim.user_id == u.id and not u.is_superuser:
        return False  # свою задачу не приймає ніхто, крім власника
    return can_manage(u) or (claim.offer.checker_id is not None and claim.offer.checker_id == u.id)


def is_checker(u):
    return bool(u and u.is_authenticated and TaskOffer.objects.filter(checker_id=u.id, archived=False).exists())


def staff_users():
    U = get_user_model()
    qs = U.objects.filter(is_active=True).exclude(username__startswith="b24_")
    if hasattr(U, "AccountKind"):
        qs = qs.exclude(account_kind=U.AccountKind.CLIENT)
    return [{"id": u.id, "name": who(u)} for u in qs.order_by("first_name", "username")]


# ─────────────────────────── стандарт і фонд ───────────────────────────

def standard_info(user, period=None):
    """Остання оцінка основного стандарту людини не пізніше period. None — стандарту в ставці немає."""
    from django.apps import apps as dj
    period = period or month_of()
    if not user or not dj.is_installed("apps.payroll"):
        return None
    try:
        from apps.payroll.models import PayComponent
        comps = list(PayComponent.objects.filter(scheme__user=user, scheme__purpose="official", scheme__status="active",
                                                 kind="standard", active=True))
    except Exception:
        return None
    if not comps:
        return None
    best = None
    for c in comps:
        for k, v in ((c.params or {}).get("scores") or {}).items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if valid_period(k) and k <= period and (best is None or k > best[0]):
                best = (k, f)
    if not best:
        return {"score": None, "pct": None, "period": None, "ok": True, "warning": ""}
    k, f = best
    ok = f >= MIN_STANDARD - 1e-9
    pct = round(f * 100)
    warn = "" if ok else (
        f"Ваш основний стандарт за {k[5:7]}.{k[:4]} — {pct}% (правило біржі: від {round(MIN_STANDARD * 100)}%). "
        "Взяти задачу можна, але спершу — основна робота; перевіряючий побачить це попередження.")
    return {"score": f, "pct": pct, "period": k, "ok": ok, "warning": warn}


def fund_article():
    try:
        from apps.finance.models import FinModelArticle
        return FinModelArticle.objects.filter(name__iexact=FUND_NAME).order_by("-active", "id").first()
    except Exception:
        return None


def _estimate(price, qty, unit):
    return (price or D0) * (qty or D0) if unit != "pct" else D0


def fund_info(period=None):
    period = period or month_of()
    a = fund_article()
    limit = Decimal(str(a.value or 0)) if (a and a.active) else D0
    used = TaskClaim.objects.filter(status="accepted", payroll_period=period).aggregate(s=Sum("amount"))["s"] or D0
    reserved = D0
    if period == month_of():
        for p, q, u in TaskClaim.objects.filter(status__in=ACTIVE).values_list("price", "qty", "unit"):
            reserved += _estimate(p, q, u)
    enforced = limit > 0
    left = (limit - used - reserved) if enforced else None
    warn = ""
    if not a:
        warn = f"У Фінмоделі немає статті «{FUND_NAME}» — ліміт фонду не діє"
    elif not enforced:
        warn = f"Стаття «{FUND_NAME}» = 0 ₴ — ліміт фонду не діє"
    return {"name": FUND_NAME, "found": bool(a), "article_id": a.id if a else None, "period": period,
            "limit": money(limit) if enforced else None, "used": money(used), "reserved": money(reserved),
            "left": money(left) if left is not None else None, "enforced": enforced, "warning": warn}


def _run_approved(user, period):
    try:
        from apps.payroll.runs import active_run
        return active_run(user, period) is not None
    except Exception:
        return False


def default_period(user):
    """Місяць ЗП для прийнятої задачі: поточний; якщо відомість людини за нього вже затверджено — наступний."""
    p = month_of()
    for _ in range(3):
        if not _run_approved(user, p):
            return p
        p = next_month(p)
    return p


# ─────────────────────────── зайнятість і ліміти ───────────────────────────

def _period_q(period):
    q = Q(status="accepted", payroll_period=period)
    if period == month_of():
        q |= Q(status__in=ACTIVE)
    return q


def usage(offer_ids, period=None):
    """Скільки одиниць задачі «зайнято» в місяці: прийняте цього місяця + взяте в роботу зараз."""
    period = period or month_of()
    out = defaultdict(lambda: {"used": D0, "by_user": defaultdict(lambda: D0), "active": []})
    ids = list(offer_ids)
    if not ids:
        return out
    for c in TaskClaim.objects.filter(offer_id__in=ids).filter(_period_q(period)).select_related("user"):
        r = out[c.offer_id]
        r["used"] += c.qty or D0
        r["by_user"][c.user_id] += c.qty or D0
        if c.status in ACTIVE:
            r["active"].append(c)
    return out


def offer_json(o, viewer=None, st=None):
    d = {"id": o.id, "category_id": o.category_id, "category_name": o.category.name, "department": o.category.department,
         "title": o.title, "how_to": o.how_to, "done_criteria": o.done_criteria,
         "proof_type": o.proof_type, "proof_label": PROOF_LABELS.get(o.proof_type, o.proof_type),
         "price": money(o.price), "unit": o.unit, "unit_label": o.unit_label, "unit_text": unit_text(o.unit, o.unit_label, o.price),
         "monthly_limit_qty": o.monthly_limit_qty, "max_per_person": o.max_per_person, "max_takers": o.max_takers,
         "due_days": o.due_days, "checker_id": o.checker_id, "checker_name": who(o.checker) if o.checker_id else "",
         "active": o.active, "archived": o.archived, "order": o.order, "note": o.note}
    if st is not None and viewer is not None:
        used = st["used"]
        mine = st["by_user"].get(viewer.id, D0)
        act = st["active"]
        my = next((c for c in act if c.user_id == viewer.id), None)
        others = [c for c in act if c.user_id != viewer.id]
        state = "free"
        if my:
            state = "mine"
        elif o.max_takers and len({c.user_id for c in others}) >= o.max_takers:
            state = "busy"
        elif o.monthly_limit_qty and used >= o.monthly_limit_qty:
            state = "limit"
        elif o.max_per_person and mine >= o.max_per_person:
            state = "person_limit"
        d.update({"state": state, "used_qty": float(used), "my_qty": float(mine),
                  "left_qty": float(max(D0, o.monthly_limit_qty - used)) if o.monthly_limit_qty else None,
                  "my_claim_id": my.id if my else None,
                  "busy_by": [{"name": who(c.user), "due_at": _iso(c.due_at), "status": c.status} for c in others][:5]})
    return d


def category_json(c):
    return {"id": c.id, "department": c.department, "department_label": DEPARTMENT_LABELS.get(c.department, c.department),
            "name": c.name, "order": c.order, "active": c.active}


def board(viewer):
    manage = can_manage(viewer)
    period = month_of()
    cats = TaskCategory.objects.filter(archived=False)
    offers = TaskOffer.objects.filter(archived=False, category__archived=False).select_related("category", "checker")
    if not manage:
        cats = cats.filter(active=True)
        offers = offers.filter(active=True, category__active=True)
    cats, offers = list(cats), list(offers)
    st = usage([o.id for o in offers], period)
    deps = []
    for k, label in DEPARTMENTS:
        mine = [o for o in offers if o.category.department == k]
        deps.append({"key": k, "label": label, "n_active": sum(1 for o in mine if o.active and o.category.active), "n_total": len(mine)})
    review_q = TaskClaim.objects.filter(status="submitted")
    if not viewer.is_superuser:
        review_q = review_q.exclude(user=viewer)
    if not manage:
        review_q = review_q.filter(offer__checker=viewer)
    out = {
        "month": period,
        "departments": deps,
        "categories": [category_json(c) for c in cats],
        "offers": [offer_json(o, viewer, st[o.id]) for o in offers],
        "units": [{"key": k, "label": v} for k, v in TaskOffer.UNIT],
        "proofs": [{"key": k, "label": v} for k, v in TaskOffer.PROOF],
        "me": {"id": viewer.id, "name": who(viewer), "can_manage": manage, "can_review": manage or is_checker(viewer),
               "standard": standard_info(viewer, period), "min_standard_pct": round(MIN_STANDARD * 100),
               "active_claims": TaskClaim.objects.filter(user=viewer, status__in=ACTIVE).count()},
        "review_count": review_q.count() if (manage or is_checker(viewer)) else 0,
        "fund": fund_info(period) if manage else None,
    }
    if manage:
        out["users"] = staff_users()
        out["archived_offers"] = [{"id": o.id, "title": o.title, "category_name": o.category.name,
                                   "department": o.category.department}
                                  for o in TaskOffer.objects.filter(archived=True).select_related("category").order_by("-updated_at")[:200]]
    return out


# ─────────────────────────── «Беру» → здати → прийняти ───────────────────────────

def _lock_claim(pk):
    c = TaskClaim.objects.select_for_update().filter(pk=pk).first()
    if not c:
        raise BountyError("Задачу не знайдено", 404)
    return c


@transaction.atomic
def take(offer_id, user, qty=None):
    if not can_view(user):
        raise BountyError("Немає доступу до біржі задач", 403)
    o = TaskOffer.objects.select_for_update().filter(pk=offer_id).first()
    if not o:
        raise BountyError("Задачу не знайдено", 404)
    cat = o.category
    if o.archived or not o.active or cat.archived or not cat.active:
        raise BountyError("Задача зараз не активна — її вмикає власник", 409, "inactive")
    q = D1 if o.unit in ("task", "pct") else dec(qty, D1, lo=Decimal("0.01"), hi=Decimal("100000"), field="Кількість")
    period = month_of()
    st = usage([o.id], period)[o.id]
    act = st["active"]
    if any(c.user_id == user.id for c in act):
        raise BountyError("Ви вже взяли цю задачу — здайте її або відмовтеся", 409, "already")
    if o.max_takers and len({c.user_id for c in act}) >= o.max_takers:
        names = ", ".join(sorted({who(c.user) for c in act}))
        raise BountyError(f"Зайнято: цю задачу вже виконує {names}", 409, "busy")
    if o.monthly_limit_qty and st["used"] + q > o.monthly_limit_qty:
        left = max(D0, o.monthly_limit_qty - st["used"])
        raise BountyError(f"Ліміт на місяць вичерпано (залишилось {fmt(left)})", 409, "limit")
    mine = st["by_user"].get(user.id, D0)
    if o.max_per_person and mine + q > o.max_per_person:
        raise BountyError(f"Ваш ліміт на місяць для цієї задачі: {o.max_per_person} (уже {fmt(mine)})", 409, "person_limit")
    est = _estimate(o.price, q, o.unit)
    f = fund_info(period)
    if f["enforced"] and est > 0 and Decimal(str(f["left"])) < est:
        raise BountyError("Фонд «Біржа задач» на цей місяць вичерпано — зверніться до власника", 409, "fund")
    std = standard_info(user, period) or {}
    now = timezone.now()
    c = TaskClaim.objects.create(
        offer=o, user=user, qty=q, price=o.price, unit=o.unit, status="taken", taken_at=now,
        due_at=now + timedelta(days=max(1, int(o.due_days or 1))),
        std_score=std.get("score"), std_warning=(std.get("warning") or "")[:255],
        history=[_ev(user, "take", f"кількість {fmt(q)}" if o.unit in ("piece", "hour") else "")])
    return c, std.get("warning") or ""


@transaction.atomic
def submit(claim_id, user, proof_text="", proof_url="", qty=None):
    c = _lock_claim(claim_id)
    if c.user_id != user.id:
        raise BountyError("Здати може лише той, хто взяв задачу", 403)
    if c.status not in ("taken", "rework"):
        raise BountyError(f"Задача в статусі «{STATUS_LABELS.get(c.status)}» — здати не можна", 409)
    text = (proof_text or "").strip()
    url = (proof_url or "").strip()[:500]
    if url and not re.match(r"^https?://", url, re.I):
        raise BountyError("Посилання має починатися з http:// або https://")
    has_file = c.files.exists()
    pt = c.offer.proof_type
    if pt == "link" and not url:
        raise BountyError("Для цієї задачі потрібне посилання на результат")
    if pt == "photo" and not (has_file or url):
        raise BountyError("Для цієї задачі потрібне фото / файл (або посилання на папку з фото)")
    if pt == "text" and len(text) < 10:
        raise BountyError("Для цієї задачі потрібен короткий текстовий звіт (від 10 символів)")
    if not (text or url or has_file):
        raise BountyError("Додайте доказ: посилання, фото або текст")
    if c.unit in ("piece", "hour") and qty not in (None, ""):
        c.qty = dec(qty, lo=Decimal("0.01"), hi=Decimal("100000"), field="Кількість")
    c.proof_text, c.proof_url = text, url
    c.status = "submitted"
    c.submitted_at = timezone.now()
    c.history = [*(c.history or []), _ev(user, "submit", f"кількість {fmt(c.qty)}" if c.unit in ("piece", "hour") else "")]
    c.save()
    return c


@transaction.atomic
def accept(claim_id, user, qty=None, base_amount=None, amount=None, quality=None, comment="", period=None, force=False):
    c = _lock_claim(claim_id)
    if not can_review(user, c):
        raise BountyError("Приймати може власник або призначений перевіряючий (свою задачу — не можна)", 403)
    if c.status != "submitted":
        raise BountyError(f"Задача в статусі «{STATUS_LABELS.get(c.status)}» — прийняти не можна", 409)
    manage = can_manage(user)
    if c.unit in ("piece", "hour") and qty not in (None, ""):
        c.qty = dec(qty, lo=Decimal("0.01"), hi=Decimal("100000"), field="Кількість")
    if c.unit == "pct":
        b = dec(base_amount, None, lo=D0, field="Сума оплат")
        if b is None:
            b = c.base_amount
        if b is None:
            raise BountyError("Вкажіть суму оплат, з якої рахуємо відсоток")
        c.base_amount = b
        calc = b * c.price / Decimal("100")
    else:
        calc = c.price * c.qty
    amt = calc
    if amount not in (None, ""):
        if not manage:
            raise BountyError("Змінити суму вручну може лише власник («Керувати біржею задач»)", 403)
        amt = dec(amount, lo=D0, hi=Decimal("1000000"), field="Сума")
    amt = amt.quantize(Decimal("0.01"), ROUND_HALF_UP)
    if period:
        if not valid_period(period):
            raise BountyError("Місяць ЗП у форматі РРРР-ММ")
        if _run_approved(c.user, period):
            raise BountyError(f"ЗП за {period} уже затверджено — оберіть наступний місяць", 409, "run_approved")
    else:
        period = default_period(c.user)
    q = None
    if quality not in (None, "", 0, "0"):
        q = to_int(quality, "Оцінка", 1, 5)
    force = bool(force) and manage
    o = c.offer
    if o.monthly_limit_qty and not force:
        done = (TaskClaim.objects.filter(offer=o, status="accepted", payroll_period=period).exclude(pk=c.pk)
                .aggregate(s=Sum("qty"))["s"] or D0)
        if done + c.qty > o.monthly_limit_qty:
            raise BountyError(f"Прийнято вже {fmt(done)} з {o.monthly_limit_qty} на місяць — ліміт буде перевищено",
                              409, "limit", {"can_force": manage})
    f = fund_info(period)
    if f["enforced"] and not force and Decimal(str(f["used"])) + amt > Decimal(str(f["limit"])):
        raise BountyError(f"Фонд «{FUND_NAME}» за {period}: прийнято {fmt(f['used'])} з {fmt(f['limit'])} ₴ — сума перевищить ліміт",
                          409, "fund", {"can_force": manage})
    now = timezone.now()
    c.amount = amt
    c.quality = q
    c.payroll_period = period
    c.status = "accepted"
    c.reviewer = user
    c.reviewed_at = now
    c.comment = (comment or "").strip()[:2000]
    note = f"{fmt(amt)} ₴ у ЗП за {period}" + (" (понад ліміт — рішення керівника)" if force else "")
    c.history = [*(c.history or []), _ev(user, "accept", note)]
    c.save()
    return c


@transaction.atomic
def rework(claim_id, user, comment=""):
    c = _lock_claim(claim_id)
    if not can_review(user, c):
        raise BountyError("Повернути на доробку може власник або призначений перевіряючий", 403)
    if c.status != "submitted":
        raise BountyError(f"Задача в статусі «{STATUS_LABELS.get(c.status)}» — повернути не можна", 409)
    text = (comment or "").strip()
    if len(text) < 3:
        raise BountyError("Напишіть, що саме доробити")
    now = timezone.now()
    c.status = "rework"
    c.comment = text[:2000]
    c.reviewer = user
    c.reviewed_at = now
    c.due_at = now + timedelta(days=max(1, int(c.offer.due_days or 1)))
    c.history = [*(c.history or []), _ev(user, "rework", text)]
    c.save()
    return c


@transaction.atomic
def cancel(claim_id, user, comment=""):
    c = _lock_claim(claim_id)
    own = c.user_id == user.id
    manage = can_manage(user)
    if c.status in ("taken", "rework") and own:
        pass
    elif c.status in ACTIVE and manage:
        pass
    elif c.status == "accepted" and manage:
        if _run_approved(c.user, c.payroll_period):
            raise BountyError(f"ЗП за {c.payroll_period} уже затверджено — скасувати прийняття не можна", 409, "run_approved")
    elif c.status == "cancelled":
        raise BountyError("Задачу вже скасовано", 409)
    else:
        raise BountyError("Скасувати може той, хто взяв (до здачі), або власник", 403)
    text = (comment or "").strip()
    c.history = [*(c.history or []), _ev(user, "cancel", text or ("відмова виконавця" if own else "знято керівником"))]
    c.status = "cancelled"
    if text:
        c.comment = text[:2000]
    c.save()
    return c


# ─────────────────────────── списки ───────────────────────────

def claim_json(c, viewer):
    o = c.offer
    now = timezone.now()
    own = c.user_id == viewer.id
    manage = can_manage(viewer)
    return {
        "id": c.id, "offer_id": o.id, "offer_title": o.title, "category_name": o.category.name,
        "department": o.category.department, "department_label": DEPARTMENT_LABELS.get(o.category.department, ""),
        "unit": c.unit, "unit_label": o.unit_label, "unit_text": unit_text(c.unit, o.unit_label, c.price),
        "price": money(c.price), "qty": float(c.qty or 0), "base_amount": money(c.base_amount) if c.base_amount is not None else None,
        "amount": money(c.amount), "estimate": money(_estimate(c.price, c.qty, c.unit)),
        "status": c.status, "status_label": STATUS_LABELS.get(c.status, c.status),
        "user_id": c.user_id, "user_name": who(c.user),
        "taken_at": _iso(c.taken_at), "due_at": _iso(c.due_at), "submitted_at": _iso(c.submitted_at),
        "overdue": bool(c.status in ("taken", "rework") and c.due_at and c.due_at < now),
        "proof_text": c.proof_text, "proof_url": c.proof_url, "proof_type": o.proof_type,
        "proof_label": PROOF_LABELS.get(o.proof_type, ""), "done_criteria": o.done_criteria, "how_to": o.how_to,
        "files": [{"id": f.id, "filename": f.filename, "content_type": f.content_type, "size": f.size} for f in c.files.all()],
        "reviewer_name": who(c.reviewer) if c.reviewer_id else "", "reviewed_at": _iso(c.reviewed_at),
        "comment": c.comment, "quality": c.quality, "payroll_period": c.payroll_period,
        "std_warning": c.std_warning, "history": c.history or [],
        "can_submit": own and c.status in ("taken", "rework"),
        "can_review": c.status == "submitted" and can_review(viewer, c),
        "can_cancel": (own and c.status in ("taken", "rework")) or (manage and c.status in ACTIVE + ("accepted",)),
        "can_force": manage,
    }


def claims_qs():
    return (TaskClaim.objects.select_related("offer__category", "offer__checker", "user", "reviewer")
            .prefetch_related(Prefetch("files", queryset=ClaimFile.objects.defer("data").order_by("id"))))


def list_claims(viewer, scope="mine", status="", month="", user_id=None):
    manage = can_manage(viewer)
    qs = claims_qs()
    if scope == "review":
        qs = qs.filter(status="submitted")
        if not viewer.is_superuser:
            qs = qs.exclude(user=viewer)
        if not manage:
            qs = qs.filter(offer__checker=viewer)
        qs = qs.order_by("submitted_at", "id")
    elif scope == "all":
        if not manage:
            raise BountyError("Усі задачі команди бачить власник («Керувати біржею задач»)", 403)
        if user_id:
            qs = qs.filter(user_id=user_id)
    else:
        qs = qs.filter(user=viewer)
    if status:
        if status == "active":
            qs = qs.filter(status__in=ACTIVE)
        elif status in STATUS_LABELS:
            qs = qs.filter(status=status)
    if month and valid_period(month):
        y, m = int(month[:4]), int(month[5:7])
        qs = qs.filter(Q(status="accepted", payroll_period=month) |
                       (~Q(status="accepted") & Q(taken_at__year=y, taken_at__month=m)))
    return [claim_json(c, viewer) for c in qs[:300]]


def summary(viewer, period):
    """Підсумки місяця: хто скільки заробив на біржі, по напрямах, сильні сторони (за 3 місяці)."""
    manage = can_manage(viewer)
    base = TaskClaim.objects.filter(status="accepted", payroll_period=period).select_related("offer__category", "user")
    if not manage:
        base = base.filter(user=viewer)
    people, cats = {}, {}
    for c in base:
        p = people.setdefault(c.user_id, {"user_id": c.user_id, "name": who(c.user), "count": 0, "amount": D0,
                                          "q_sum": 0, "q_n": 0, "reworks": 0, "on_time": 0, "by_department": defaultdict(lambda: D0)})
        p["count"] += 1
        p["amount"] += c.amount or D0
        if c.quality:
            p["q_sum"] += c.quality
            p["q_n"] += 1
        p["reworks"] += sum(1 for e in (c.history or []) if e.get("act") == "rework")
        if c.submitted_at and c.due_at and c.submitted_at <= c.due_at:
            p["on_time"] += 1
        p["by_department"][c.offer.category.department] += c.amount or D0
        k = c.offer.category_id
        r = cats.setdefault(k, {"category_id": k, "name": c.offer.category.name, "department": c.offer.category.department,
                                "department_label": DEPARTMENT_LABELS.get(c.offer.category.department, ""), "count": 0, "amount": D0})
        r["count"] += 1
        r["amount"] += c.amount or D0
    window = [period, prev_month(period), prev_month(prev_month(period))]
    strengths = defaultdict(dict)
    if people:
        for row in (TaskClaim.objects.filter(status="accepted", payroll_period__in=window, user_id__in=list(people))
                    .values("user_id", "offer__category__name", "quality")):
            s = strengths[row["user_id"]].setdefault(row["offer__category__name"], {"n": 0, "q_sum": 0, "q_n": 0})
            s["n"] += 1
            if row["quality"]:
                s["q_sum"] += row["quality"]
                s["q_n"] += 1
    rows = []
    for uid, p in people.items():
        tops = []
        for name, s in sorted(strengths[uid].items(), key=lambda kv: (-kv[1]["n"], kv[0])):
            avg = (s["q_sum"] / s["q_n"]) if s["q_n"] else None
            if avg is not None and avg < 4:
                continue
            tops.append(f"{name} — {s['n']}" + (f" (якість {avg:.1f})" if avg is not None else ""))
            if len(tops) >= 2:
                break
        rows.append({"user_id": uid, "name": p["name"], "count": p["count"], "amount": money(p["amount"]),
                     "avg_quality": round(p["q_sum"] / p["q_n"], 1) if p["q_n"] else None, "reworks": p["reworks"],
                     "on_time_pct": round(p["on_time"] * 100 / p["count"]) if p["count"] else None,
                     "by_department": [{"key": k, "label": DEPARTMENT_LABELS.get(k, k), "amount": money(v)}
                                       for k, v in sorted(p["by_department"].items(), key=lambda kv: -kv[1])],
                     "strengths": tops})
    rows.sort(key=lambda r: -r["amount"])
    cat_rows = sorted(({**r, "amount": money(r["amount"])} for r in cats.values()), key=lambda r: -r["amount"])
    return {"period": period, "people": rows, "categories": cat_rows, "total": money(sum(Decimal(str(r["amount"])) for r in rows)),
            "fund": fund_info(period) if manage else None, "can_manage": manage}


# ─────────────────────────── прайс ───────────────────────────

TEXT_LIMITS = {"how_to": 6000, "done_criteria": 3000, "note": 255, "unit_label": 40}


def apply_offer_fields(o, d, partial):
    if "title" in d or not partial:
        title = str(d.get("title") or "").strip()
        if not title:
            raise BountyError("Назва задачі обовʼязкова")
        o.title = title[:200]
    if "category_id" in d or not partial:
        cat = TaskCategory.objects.filter(pk=d.get("category_id") or 0, archived=False).first()
        if not cat:
            raise BountyError("Оберіть напрям")
        o.category = cat
    for f, lim in TEXT_LIMITS.items():
        if f in d:
            setattr(o, f, str(d.get(f) or "")[:lim])
    if "proof_type" in d:
        if d["proof_type"] not in PROOF_LABELS:
            raise BountyError("Невідомий тип доказу")
        o.proof_type = d["proof_type"]
    if "unit" in d:
        if d["unit"] not in UNIT_LABELS:
            raise BountyError("Невідома одиниця")
        o.unit = d["unit"]
    if "price" in d:
        o.price = dec(d.get("price"), D0, lo=D0, hi=Decimal("1000000"), field="Ціна")
    if o.unit == "pct" and (o.price or D0) > 100:
        raise BountyError("Відсоток — не більше 100")
    for f, label, lo, hi in (("monthly_limit_qty", "Ліміт на місяць", 0, 100000), ("max_per_person", "Ліміт на людину", 0, 100000),
                             ("max_takers", "Скільки людей одночасно", 0, 100), ("due_days", "Термін, днів", 1, 90),
                             ("order", "Порядок", 0, 1000000)):
        if f in d:
            setattr(o, f, to_int(d.get(f), label, lo, hi))
    if "checker_id" in d:
        cid = d.get("checker_id")
        if cid in (None, "", 0, "0"):
            o.checker = None
        else:
            U = get_user_model()
            u = U.objects.filter(pk=cid, is_active=True).first()
            if not u:
                raise BountyError("Перевіряючого не знайдено")
            o.checker = u
    if "active" in d:
        o.active = to_bool(d.get("active"))
    return o


def _siblings(obj):
    if isinstance(obj, TaskOffer):
        return list(TaskOffer.objects.filter(category_id=obj.category_id, archived=False).order_by("order", "id"))
    return list(TaskCategory.objects.filter(department=obj.department, archived=False).order_by("order", "id"))


@transaction.atomic
def move(obj, direction):
    items = _siblings(obj)
    for i, it in enumerate(items):
        if it.order != (i + 1) * 10:
            it.order = (i + 1) * 10
            it.save(update_fields=["order"])
    idx = next((i for i, it in enumerate(items) if it.pk == obj.pk), None)
    if idx is None:
        return
    j = idx - 1 if direction == "up" else idx + 1
    if j < 0 or j >= len(items):
        return
    a, b = items[idx], items[j]
    a.order, b.order = b.order, a.order
    a.save(update_fields=["order"])
    b.save(update_fields=["order"])


def next_order(model, **flt):
    last = model.objects.filter(archived=False, **flt).order_by("-order").values_list("order", flat=True).first()
    return (last or 0) + 10
