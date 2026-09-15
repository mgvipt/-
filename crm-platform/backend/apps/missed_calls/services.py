"""Черга «Пропущені»: жива обробка дзвінків, задачі, передача колезі, ескалація, звіт.

Нічого не надсилає клієнтам. Сповіщення — лише всередині CRM (inbox.Notification) співробітникам.
"""
import logging
from datetime import datetime, timedelta

from django.conf import settings as dj_settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import engine
from .models import MissedCallItem, MissedCallSettings

log = logging.getLogger(__name__)

OPEN_TASK_STATUSES = ["proposed", "open", "in_progress"]


# ── довідкові ──

def calendar(cfg=None) -> engine.WorkCalendar:
    cfg = cfg or MissedCallSettings.get()
    days = set()
    for d in cfg.work_days or []:
        try:
            if 0 <= int(d) <= 6:
                days.add(int(d))
        except (TypeError, ValueError):
            pass
    return engine.WorkCalendar(start=cfg.work_start, end=cfg.work_end,
                               days=frozenset(days or range(7)), tz=dj_settings.TIME_ZONE)


def call_ts(call):
    return call.started_at or call.created_at or timezone.now()


def _staff_qs():
    from apps.accounts.models import User
    return (User.objects.filter(is_active=True, account_kind=User.AccountKind.STAFF)
            .exclude(employment_status="dismissed"))


def active_staff_ids():
    return set(_staff_qs().values_list("id", flat=True))


def eligible_ids():
    """Кому МОЖНА призначати пропущені: активні співробітники з правом «Доступ до телефонії»
    (інакше людина не бачить черги — напр. склад у черзі дзвінків або старі акаунти з Бітрикса)."""
    return {u.id for u in _staff_qs().select_related("role", "department") if can_use(u)}


def user_name(u):
    if not u:
        return ""
    return (u.get_full_name() or u.username or "").strip()


def ignored_numbers(cfg):
    """Номери, що не потрапляють у чергу: вручну вказані, наші SIM-лінії, телефони співробітників."""
    from apps.telephony.models import PhoneLine
    out = {engine.norm9(n) for n in (cfg.ignore_numbers or [])}
    out |= {engine.norm9(n) for n in PhoneLine.objects.values_list("number", flat=True)}
    if cfg.ignore_staff_numbers:
        out |= {engine.norm9(p) for p in _staff_qs().exclude(phone="").values_list("phone", flat=True)}
    return {x for x in out if len(x) >= 7}


def last_manager_id(contact):
    """Останній менеджер клієнта: власник найсвіжішої угоди, інакше найсвіжішого ліда."""
    if not contact:
        return None
    from apps.crm.models import Deal, Lead
    uid = (Deal.objects.filter(contact=contact, owner__isnull=False)
           .order_by("-created_at").values_list("owner_id", flat=True).first())
    if uid:
        return uid
    return (Lead.objects.filter(contact=contact, owner__isnull=False)
            .order_by("-created_at").values_list("owner_id", flat=True).first())


def on_duty_ids():
    """Хто на зміні (почав робочий день у табелі) серед учасників черги вхідних, у порядку черги.
    Хто на паузі (обід) — лише якщо більше нікого немає."""
    from apps.finance.models import WorkSession
    from apps.telephony.models import CallQueueMember
    sessions = list(WorkSession.objects.filter(ended_at__isnull=True).values_list("user_id", "paused_at"))
    working = {u for u, p in sessions if p is None}
    paused = {u for u, p in sessions if p is not None}
    members = list(CallQueueMember.objects.filter(enabled=True, user__is_active=True)
                   .order_by("position", "id").values_list("user_id", flat=True))
    duty = [u for u in members if u in working]
    return duty or [u for u in members if u in paused]


def _open_counts(user_ids):
    rows = (MissedCallItem.objects.filter(status="open", assignee_id__in=list(user_ids))
            .values("assignee_id").annotate(n=Count("id")))
    return {r["assignee_id"]: r["n"] for r in rows}


def pick_responsible(contact):
    duty = on_duty_ids()
    return engine.choose_responsible(
        contact.owner_id if contact else None, last_manager_id(contact),
        duty, _open_counts(duty), eligible_ids())


def display_name(item):
    if item.contact_id and item.contact:
        nm = str(item.contact).strip()
        if nm:
            return nm
    return item.number or item.phone9


def _hist(item, event, **kw):
    h = list(item.history or [])
    h.append({"at": timezone.now().isoformat(), "event": event, **kw})
    item.history = h[-30:]


# ── задачі ──

def _create_task(item):
    from apps.crm.models import Task
    loc = timezone.localtime(item.first_missed_at)
    body = (f"Пропущений дзвінок {loc:%d.%m %H:%M} на лінію «{item.line or '—'}». Номер: {item.number}.\n"
            f"Передзвоніть до {timezone.localtime(item.due_at):%d.%m %H:%M}. "
            f"Задача закриється сама, щойно з цим номером буде розмова.")
    task = Task.objects.create(
        kind="manager", title=f"Передзвонити: {display_name(item)}"[:255], body=body, priority="high",
        contact_id=item.contact_id, deal_id=item.deal_id, assignee_id=item.assignee_id,
        status="open", due_at=item.due_at)
    item.task = task
    item.save(update_fields=["task"])
    return task


def _close_task(item):
    if item.task_id:
        from apps.crm.models import Task
        Task.objects.filter(id=item.task_id, status__in=OPEN_TASK_STATUSES).update(status="done")


# ── жива обробка дзвінка ──

def process_call(call):
    """Викликається на КОЖЕН новий Call (post_save). Повертає пункт черги або None."""
    kind = engine.classify(call.direction, call.disposition)
    if not kind:
        return None
    number = engine.external_number(call.direction, call.from_number, call.to_number)
    n9 = engine.norm9(number)
    if len(n9) < 7:
        return None
    cfg = MissedCallSettings.get()
    cal = calendar(cfg)
    ts = call_ts(call)
    with transaction.atomic():
        if kind == "missed":
            return _on_missed(call, cfg, cal, n9, number, ts)
        _on_other(call, kind, n9, ts, cal)
    return None


def _on_missed(call, cfg, cal, n9, number, ts):
    if cfg.active_since and ts < cfg.active_since - timedelta(minutes=10):
        return None  # стара історія — лише через missed_calls_backfill
    lk = engine.line_key(call.line)
    if n9 == lk or n9 in ignored_numbers(cfg):
        return None
    if MissedCallItem.objects.filter(call_ids__contains=[call.id]).exists():
        return None
    item = (MissedCallItem.objects.select_for_update()
            .filter(phone9=n9, line_key=lk, status="open").order_by("-first_missed_at").first())
    if item:
        item.call_ids = list(item.call_ids or []) + [call.id]
        item.calls_count = (item.calls_count or 0) + 1
        item.last_missed_at = max(item.last_missed_at, ts)
        if not item.contact_id and call.contact_id:
            item.contact_id = call.contact_id
        item.save(update_fields=["call_ids", "calls_count", "last_missed_at", "contact"])
        return item
    assignee_id, reason = pick_responsible(call.contact)
    item = MissedCallItem(
        phone9=n9, number=number[:32], line=(call.line or "")[:60], line_key=lk,
        contact_id=call.contact_id, deal_id=call.deal_id, first_call=call, call_ids=[call.id], calls_count=1,
        first_missed_at=ts, last_missed_at=ts, assignee_id=assignee_id, assign_reason=reason,
        due_at=cal.add_work_minutes(ts, cfg.sla_minutes))
    _hist(item, "created", to=assignee_id, reason=reason)
    item.save()
    _apply_later_calls(item, cal)          # CDR міг прийти не по порядку: розмова вже є в журналі
    if item.status == "open" and cfg.auto_task:
        _create_task(item)
    return item


def _later_calls(item):
    from apps.telephony.models import Call
    return (Call.objects.filter(Q(from_number__endswith=item.phone9) | Q(to_number__endswith=item.phone9),
                                started_at__gte=item.first_missed_at)
            .exclude(id__in=list(item.call_ids or [])).order_by("started_at", "id"))


def _apply_later_calls(item, cal):
    """Звірити пункт з дзвінками ПІСЛЯ пропуску (страховка від CDR не по порядку). Повертає True, якщо змінено."""
    changed = False
    for c in _later_calls(item):
        kind = engine.classify(c.direction, c.disposition)
        if kind not in ("answered_out", "attempt_out", "answered_in"):
            continue
        if engine.norm9(engine.external_number(c.direction, c.from_number, c.to_number)) != item.phone9:
            continue
        ts = call_ts(c)
        if kind in ("answered_out", "attempt_out"):
            changed |= engine.register_attempt(item, ts, cal)
        if kind in ("answered_out", "answered_in") and engine.close_by_call(item, kind, ts, c.id):
            _hist(item, "closed", reason=item.close_reason, call=c.id)
            changed = True
            break
    if changed:
        item.save()
    return changed


def _on_other(call, kind, n9, ts, cal):
    items = list(MissedCallItem.objects.select_for_update()
                 .filter(phone9=n9, status="open", first_missed_at__lte=ts))
    for item in items:
        changed = False
        if kind in ("answered_out", "attempt_out"):
            changed |= engine.register_attempt(item, ts, cal)
        if kind in ("answered_out", "answered_in") and engine.close_by_call(item, kind, ts, call.id):
            _hist(item, "closed", reason=item.close_reason, call=call.id)
            changed = True
        if changed:
            item.save()
            if item.status == "closed":
                _close_task(item)


# ── дії менеджера ──

def close_manual(item, reason, user, note=""):
    if reason not in ("other_channel", "not_relevant"):
        raise ValueError("bad reason")
    with transaction.atomic():
        item = MissedCallItem.objects.select_for_update().get(pk=item.pk)
        if item.status != "open":
            return item
        item.status = "closed"
        item.closed_at = timezone.now()
        item.close_reason = reason
        item.closed_by = user
        item.close_note = (note or "")[:300]
        _hist(item, "closed", reason=reason, by=user.id if user else None)
        item.save()
        _close_task(item)
    return item


def transfer(item, to_user, by_user, note=""):
    from apps.crm.models import Task
    from apps.inbox.models import Notification
    with transaction.atomic():
        item = MissedCallItem.objects.select_for_update().get(pk=item.pk)
        old = item.assignee_id
        item.assignee = to_user
        item.assign_reason = "transfer"
        _hist(item, "transfer", frm=old, to=to_user.id, by=by_user.id if by_user else None, note=(note or "")[:200])
        item.save()
        if item.task_id:
            Task.objects.filter(id=item.task_id).update(assignee=to_user)
        who = user_name(by_user) or "Колега"
        txt = f"📞 {who} передає вам пропущений дзвінок: {display_name(item)} ({item.line or '—'}). Передзвоніть, будь ласка."
        if note:
            txt += f" Коментар: {note}"
        Notification.objects.create(user=to_user, kind="system", text=txt[:300], actor=by_user)
    return item


# ── крон: звірка, призначення, ескалація ──

def escalation_targets(cfg):
    ids = []
    for x in cfg.escalate_user_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            pass
    qs = _staff_qs()
    return list(qs.filter(id__in=ids) if ids else qs.filter(is_superuser=True))


def sweep(now=None):
    """Кожні 5 хв (крон). Нічого не надсилає клієнтам."""
    from apps.crm.models import Task
    from apps.inbox.models import Notification
    from apps.telephony.models import Call
    now = now or timezone.now()
    cfg = MissedCallSettings.get()
    cal = calendar(cfg)
    res = {"picked_up": 0, "reconciled": 0, "task_closed": 0, "assigned": 0, "escalated": 0}

    # 0) пропущені, які не обробились сигналом (помилка/рестарт) — за останню добу
    since = now - timedelta(hours=24)
    if cfg.active_since:
        since = max(since, cfg.active_since - timedelta(minutes=10))
    seen = set()
    for ids in MissedCallItem.objects.filter(first_missed_at__gte=since - timedelta(days=2)).values_list("call_ids", flat=True):
        seen.update(ids or [])
    for c in (Call.objects.filter(Q(direction="missed") | Q(direction="in", disposition__in=list(engine.MISSED_DISPOSITIONS)),
                                  started_at__gte=since).exclude(id__in=seen).order_by("started_at", "id")):
        try:
            if process_call(c):
                res["picked_up"] += 1
        except Exception:  # noqa: BLE001
            log.exception("missed_calls sweep: call %s", c.id)

    # 1) звірка з журналом (CDR не по порядку) + 2) задачу закрили руками
    for item in MissedCallItem.objects.filter(status="open"):
        with transaction.atomic():
            if _apply_later_calls(item, cal) and item.status == "closed":
                _close_task(item)
                res["reconciled"] += 1
                continue
            if item.task_id and Task.objects.filter(id=item.task_id, status__in=["done", "canceled"]).exists():
                item.status = "closed"
                item.closed_at = now
                item.close_reason = "task_closed"
                _hist(item, "closed", reason="task_closed")
                item.save()
                res["task_closed"] += 1

    # 3) нікому не призначені → черговому, щойно хтось на зміні
    duty = on_duty_ids()
    if duty:
        active = eligible_ids()
        counts = _open_counts(duty)
        for item in MissedCallItem.objects.filter(status="open", assignee__isnull=True).order_by("first_missed_at"):
            uid, reason = engine.choose_responsible(None, None, duty, counts, active)
            if not uid:
                break
            item.assignee_id, item.assign_reason = uid, reason
            _hist(item, "assigned", to=uid, reason=reason)
            item.save(update_fields=["assignee", "assign_reason", "history"])
            if item.task_id:
                Task.objects.filter(id=item.task_id).update(assignee_id=uid)
            elif cfg.auto_task:
                _create_task(item)
            counts[uid] = counts.get(uid, 0) + 1
            res["assigned"] += 1

    # 4) ескалація керівнику (лише у CRM), один раз на пункт
    targets = None
    for item in MissedCallItem.objects.filter(status="open", escalated_at__isnull=True).select_related("assignee", "contact"):
        wait = cal.work_minutes_between(item.first_missed_at, now)
        if wait < cfg.escalate_minutes:
            continue
        if not MissedCallItem.objects.filter(pk=item.pk, escalated_at__isnull=True).update(escalated_at=now):
            continue
        targets = targets if targets is not None else escalation_targets(cfg)
        who = user_name(item.assignee) or "не призначено"
        txt = (f"⚠ Пропущений без передзвону вже {wait} роб. хв: {display_name(item)} · {item.line or '—'}. "
               f"Відповідальний: {who}.")
        for u in targets:
            Notification.objects.create(user=u, kind="system", text=txt[:300])
        res["escalated"] += 1
    return res


# ── показ і звіт ──

def can_all(u):
    return bool(u.is_superuser or u.has_perm_code("telephony.view.all"))


def can_use(u):
    return bool(can_all(u) or u.has_perm_code("telephony.view"))


def can_report(u):
    return bool(u.is_superuser or u.has_perm_code("telephony.calls") or u.has_perm_code("telephony.view.all")
                or u.has_perm_code("roles.manage"))


def can_settings(u):
    return bool(u.is_superuser or u.has_perm_code("roles.manage") or u.has_perm_code("telephony.queue"))


def can_touch(u, item):
    return can_all(u) or item.assignee_id in (None, u.id)


def visible_qs(u, scope="auto"):
    qs = MissedCallItem.objects.select_related("assignee", "contact", "task")
    if scope == "all" and can_all(u):
        return qs
    if scope == "auto" and can_all(u):
        return qs
    return qs.filter(Q(assignee=u) | Q(assignee__isnull=True))


def serialize(item, now, cal, cfg):
    end = item.closed_at if item.status == "closed" else now
    wait_work = cal.work_minutes_between(item.first_missed_at, end)
    return {
        "id": item.id, "number": item.number, "phone9": item.phone9, "line": item.line,
        "contact": item.contact_id, "contact_name": (str(item.contact).strip() if item.contact_id and item.contact else ""),
        "deal": item.deal_id, "calls_count": item.calls_count,
        "first_missed_at": item.first_missed_at, "last_missed_at": item.last_missed_at,
        "wait_min": max(0, int((end - item.first_missed_at).total_seconds() // 60)),
        "wait_work_min": wait_work,
        "due_at": item.due_at, "overdue": item.status == "open" and wait_work >= cfg.sla_minutes,
        "assignee": item.assignee_id, "assignee_name": user_name(item.assignee),
        "assign_reason": item.assign_reason, "assign_reason_label": item.get_assign_reason_display() if item.assign_reason else "",
        "task": item.task_id, "status": item.status, "closed_at": item.closed_at,
        "close_reason": item.close_reason, "close_reason_label": item.get_close_reason_display() if item.close_reason else "",
        "first_attempt_at": item.first_attempt_at, "reaction_work_min": item.reaction_work_min,
        "escalated": bool(item.escalated_at), "backfilled": item.backfilled,
    }


def summary(u, now=None):
    """Лічильник для віджета телефона (WebPhone.tsx). Лише читання."""
    now = now or timezone.now()
    out = {"enabled": can_use(u), "mine": 0, "unassigned": 0, "all": None, "overdue": 0,
           "max_id": 0, "new": [], "escalated": 0, "esc_last": 0, "esc_new": []}
    if not out["enabled"]:
        return out
    cfg = MissedCallSettings.get()
    cal = calendar(cfg)
    out["sla_minutes"] = cfg.sla_minutes
    base = MissedCallItem.objects.filter(status="open").select_related("contact", "assignee")
    mine_q = base.filter(Q(assignee=u) | Q(assignee__isnull=True))
    out["mine"] = base.filter(assignee=u).count()
    out["unassigned"] = base.filter(assignee__isnull=True).count()
    if can_all(u):
        out["all"] = base.count()
    lst = list(mine_q.order_by("-id")[:30])
    out["overdue"] = sum(1 for it in lst if cal.work_minutes_between(it.first_missed_at, now) >= cfg.sla_minutes)
    out["max_id"] = lst[0].id if lst else 0
    out["new"] = [{"id": it.id, "number": it.number, "name": display_name(it), "line": it.line,
                   "first_missed_at": it.first_missed_at} for it in lst[:5]]
    if any(t.id == u.id for t in escalation_targets(cfg)):
        esc = list(base.filter(escalated_at__isnull=False).order_by("-escalated_at")[:5])
        out["escalated"] = base.filter(escalated_at__isnull=False).count()
        out["esc_last"] = int(esc[0].escalated_at.timestamp()) if esc else 0
        out["esc_new"] = [{"id": it.id, "number": it.number, "name": display_name(it),
                           "assignee_name": user_name(it.assignee), "esc_ts": int(it.escalated_at.timestamp())} for it in esc]
    return out


def report(date_from, date_to, now=None):
    """Звіт за період (дати включно, київський час): по відповідальних і по лініях."""
    now = now or timezone.now()
    cfg = MissedCallSettings.get()
    cal = calendar(cfg)
    tz = timezone.get_current_timezone()
    start = datetime.combine(date_from, datetime.min.time(), tz)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tz)
    items = list(MissedCallItem.objects.filter(first_missed_at__gte=start, first_missed_at__lt=end)
                 .select_related("assignee"))
    by_user, by_line = {}, {}
    for it in items:
        by_user.setdefault(it.assignee_id, []).append(it)
        by_line.setdefault(it.line_key, []).append(it)
    rows_u = []
    for uid, lst in by_user.items():
        row = engine.stats(lst, cal, now, cfg.escalate_minutes)
        row.update({"user_id": uid, "name": user_name(lst[0].assignee) if uid else "Не призначено"})
        rows_u.append(row)
    # staffvis 15.09: рядки звільнених — лише з дозволом «Телефонія і звіти» (підсумок «total» рахує всі дзвінки)
    from apps.accounts.visibility import hidden_ids as _vis_hidden
    _hid = _vis_hidden("telephony", date_from)
    rows_u = [r for r in rows_u if not (r["user_id"] and r["user_id"] in _hid)]
    rows_u.sort(key=lambda r: -r["items"])
    rows_l = []
    for _k, lst in by_line.items():
        row = engine.stats(lst, cal, now, cfg.escalate_minutes)
        row["line"] = max(lst, key=lambda x: x.first_missed_at).line or "—"
        rows_l.append(row)
    rows_l.sort(key=lambda r: -r["items"])
    return {"from": date_from.isoformat(), "to": date_to.isoformat(),
            "total": engine.stats(items, cal, now, cfg.escalate_minutes),
            "by_manager": rows_u, "by_line": rows_l,
            "sla_minutes": cfg.sla_minutes, "escalate_minutes": cfg.escalate_minutes,
            "work_start": cfg.work_start.strftime("%H:%M"), "work_end": cfg.work_end.strftime("%H:%M")}
