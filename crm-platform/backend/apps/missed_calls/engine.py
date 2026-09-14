"""Чисті правила черги «Пропущені» (14.09.2026) — БЕЗ Django.

Одні й ті самі правила використовують: жива обробка дзвінків (services.py),
звіт, і сухий прогін історії (management-команда missed_calls_backfill).

Правила:
  • пропущений вхідний = відкритий пункт черги. Один пункт на (номер, лінія):
    повторні пропуски з того ж номера на ту ж лінію, поки пункт відкритий, додаються до нього;
  • будь-який ВИХІДНИЙ на цей номер після пропуску = «реакція» (спроба передзвонити);
  • пункт закривається сам, коли з цим номером була РОЗМОВА (ANSWERED) — наш вихідний
    або вхідний від клієнта (у будь-якій лінії);
  • час реакції рахується в РОБОЧИХ хвилинах (за замовчуванням 9:00–18:00, щодня).
"""
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Kyiv"
MISSED_DISPOSITIONS = {"NO ANSWER", "BUSY", "FAILED"}
MANUAL_REASONS = {"other_channel", "not_relevant", "task_closed"}


def norm9(number) -> str:
    """Останні 9 цифр номера (UA) — так само матчить клієнтів CallWebhookView."""
    return re.sub(r"\D", "", str(number or ""))[-9:]


def external_number(direction, from_number, to_number) -> str:
    """Номер клієнта: у вихідному — кому дзвонимо, у вхідному/пропущеному — хто дзвонить."""
    return (to_number if direction == "out" else from_number) or ""


def line_key(line) -> str:
    """Ключ лінії: 9 цифр її номера («Інста Онлайн · 0673812855» → 673812855),
    щоб різні підписи однієї SIM («Алмаз/Рекупер» і «Алмазне/Рекуператори») були однією лінією."""
    digits = re.sub(r"\D", "", line or "")
    if len(digits) >= 9:
        return digits[-9:]
    return (line or "").strip().lower()[:60]


def classify(direction, disposition) -> Optional[str]:
    """missed | answered_in | answered_out | attempt_out | None."""
    disp = (disposition or "").strip().upper()
    if direction == "missed":
        return "missed"
    if direction == "in":
        if disp == "ANSWERED":
            return "answered_in"
        if disp in MISSED_DISPOSITIONS:
            return "missed"
        return None
    if direction == "out":
        return "answered_out" if disp == "ANSWERED" else "attempt_out"
    return None


@dataclass
class WorkCalendar:
    """Робочий час для SLA. days — дні тижня (0=Пн … 6=Нд)."""
    start: time = time(9, 0)
    end: time = time(18, 0)
    days: frozenset = frozenset(range(7))
    tz: str = DEFAULT_TZ

    def _zone(self):
        return ZoneInfo(self.tz)

    def _valid(self):
        return bool(self.days) and self.end > self.start

    def is_work_time(self, dt: datetime) -> bool:
        if not self._valid():
            return True
        loc = dt.astimezone(self._zone())
        return loc.weekday() in self.days and self.start <= loc.time() < self.end

    def add_work_minutes(self, dt: datetime, minutes: int) -> datetime:
        """dt + N робочих хвилин. Поза робочим часом відлік стартує з початку наступного
        робочого дня: пропуск о 20:30 + 15 хв → наступний робочий день 9:15."""
        if not self._valid():
            return dt + timedelta(minutes=minutes)
        tz = self._zone()
        cur = dt.astimezone(tz)
        left = timedelta(minutes=max(0, int(minutes)))
        for _ in range(800):
            d = cur.date()
            ws = datetime.combine(d, self.start, tz)
            we = datetime.combine(d, self.end, tz)
            if d.weekday() not in self.days or cur >= we:
                cur = datetime.combine(d + timedelta(days=1), self.start, tz)
                continue
            if cur < ws:
                cur = ws
            room = we - cur
            if left <= room:
                return cur + left
            left -= room
            cur = datetime.combine(d + timedelta(days=1), self.start, tz)
        return cur + left

    def work_minutes_between(self, a: datetime, b: datetime) -> int:
        """Скільки робочих хвилин між a і b (ніч і неробочі дні не рахуються)."""
        if b is None or a is None or b <= a:
            return 0
        if not self._valid():
            return int((b - a).total_seconds() // 60)
        tz = self._zone()
        a1, b1 = a.astimezone(tz), b.astimezone(tz)
        total = 0.0
        d, last, n = a1.date(), b1.date(), 0
        while d <= last and n < 800:
            if d.weekday() in self.days:
                s = max(datetime.combine(d, self.start, tz), a1)
                e = min(datetime.combine(d, self.end, tz), b1)
                if e > s:
                    total += (e - s).total_seconds()
            d += timedelta(days=1)
            n += 1
        return int(total // 60)


def choose_responsible(owner_id, last_manager_id, on_duty, open_counts, active_ids):
    """Хто передзвонює: власник клієнта → останній менеджер клієнта → черговий на зміні
    (з черги вхідних; у кого менше відкритих пропущених) → нікого (призначить крон, щойно хтось почне день).
    Повертає (user_id | None, причина)."""
    active_ids = set(active_ids or [])
    if owner_id and owner_id in active_ids:
        return owner_id, "owner"
    if last_manager_id and last_manager_id in active_ids:
        return last_manager_id, "last_manager"
    duty = [u for u in (on_duty or []) if u in active_ids]
    if duty:
        counts = open_counts or {}
        best = min(range(len(duty)), key=lambda i: (counts.get(duty[i], 0), i))
        return duty[best], "on_duty"
    return None, ""


def register_attempt(item, ts, cal: WorkCalendar) -> bool:
    """Перший вихідний на номер після пропуску = реакція менеджера."""
    if item.first_attempt_at is None and ts >= item.first_missed_at:
        item.first_attempt_at = ts
        item.reaction_work_min = cal.work_minutes_between(item.first_missed_at, ts)
        return True
    return False


def close_by_call(item, kind, ts, call_id) -> bool:
    """Розмова з номером закриває пункт: наш вихідний → callback, вхідний клієнта → client_called."""
    reason = {"answered_out": "callback", "answered_in": "client_called"}.get(kind)
    if not reason or ts < item.first_missed_at or item.status != "open":
        return False
    item.status = "closed"
    item.closed_at = ts
    item.close_reason = reason
    item.closing_call_id = call_id
    return True


@dataclass
class Episode:
    """Пункт черги у сухому прогоні (ті самі імена полів, що у моделі MissedCallItem)."""
    phone9: str
    number: str
    line: str
    line_key: str
    first_missed_at: datetime
    last_missed_at: datetime
    due_at: datetime
    contact_id: Optional[int] = None
    call_ids: list = field(default_factory=list)
    calls_count: int = 1
    assignee_id: Optional[int] = None
    assign_reason: str = ""
    first_attempt_at: Optional[datetime] = None
    reaction_work_min: Optional[int] = None
    status: str = "open"
    closed_at: Optional[datetime] = None
    close_reason: str = ""
    closing_call_id: Optional[int] = None


def replay(calls, cal: WorkCalendar, sla_minutes=15, ignore=(), responsible: Optional[Callable] = None):
    """Прогін журналу дзвінків за правилами черги (для сухого backfill і тестів).
    calls: dict-и з ключами id, direction, disposition, from_number, to_number, line, ts (aware), contact_id.
    responsible(n9, ts, call, open_items) → (user_id, reason)."""
    ignore = set(ignore or ())
    items, open_by_key = [], {}
    for c in sorted(calls, key=lambda x: (x["ts"], x["id"])):
        kind = classify(c.get("direction"), c.get("disposition"))
        if not kind:
            continue
        number = external_number(c.get("direction"), c.get("from_number"), c.get("to_number"))
        n9 = norm9(number)
        if len(n9) < 7:
            continue
        ts = c["ts"]
        if kind == "missed":
            lk = line_key(c.get("line"))
            if n9 in ignore or n9 == lk:
                continue
            key = (n9, lk)
            it = open_by_key.get(key)
            if it is not None and it.status == "open":
                it.call_ids.append(c["id"])
                it.calls_count += 1
                it.last_missed_at = max(it.last_missed_at, ts)
                continue
            it = Episode(phone9=n9, number=number, line=(c.get("line") or "")[:60], line_key=lk,
                         first_missed_at=ts, last_missed_at=ts, due_at=cal.add_work_minutes(ts, sla_minutes),
                         contact_id=c.get("contact_id"), call_ids=[c["id"]])
            if responsible:
                it.assignee_id, it.assign_reason = responsible(n9, ts, c, [x for x in open_by_key.values() if x.status == "open"])
            items.append(it)
            open_by_key[key] = it
            continue
        for key in [k for k in open_by_key if k[0] == n9]:
            it = open_by_key[key]
            if it.status != "open":
                continue
            if kind in ("answered_out", "attempt_out"):
                register_attempt(it, ts, cal)
            if kind in ("answered_out", "answered_in") and close_by_call(it, kind, ts, c["id"]):
                del open_by_key[key]
    return items


def stats(items, cal: Optional[WorkCalendar] = None, now: Optional[datetime] = None, escalate_minutes=60):
    """Показники для звіту: скільки пропущено, % передзвонили ≤15 хв / ≤1 год (робочий час),
    не передзвонили, додзвонився сам, закрили вручну, медіана реакції."""
    items = list(items)
    n = len(items)
    react = [it.reaction_work_min for it in items if it.reaction_work_min is not None]
    react_cal = [int((it.first_attempt_at - it.first_missed_at).total_seconds() // 60)
                 for it in items if it.first_attempt_at is not None]
    no_try = [it for it in items if it.first_attempt_at is None]

    def pct(x):
        return round(100.0 * x / n) if n else 0

    cb15 = sum(1 for m in react if m <= 15)
    cb60 = sum(1 for m in react if m <= 60)
    out = {
        "items": n,
        "calls": sum(int(getattr(it, "calls_count", 1) or 1) for it in items),
        "cb15": cb15, "cb15_pct": pct(cb15),
        "cb60": cb60, "cb60_pct": pct(cb60),
        "never": sum(1 for it in no_try if it.status == "open"),
        "client_called": sum(1 for it in no_try if it.close_reason == "client_called"),
        "manual": sum(1 for it in no_try if it.close_reason in MANUAL_REASONS),
        "open": sum(1 for it in items if it.status == "open"),
        "median_work_min": int(statistics.median(react)) if react else None,
        "median_min": int(statistics.median(react_cal)) if react_cal else None,
        "cb15_cal": sum(1 for m in react_cal if m <= 15),
        "cb60_cal": sum(1 for m in react_cal if m <= 60),
    }
    if cal is not None and now is not None:
        out["would_escalate"] = sum(
            1 for it in items
            if cal.work_minutes_between(it.first_missed_at, it.first_attempt_at or it.closed_at or now) >= escalate_minutes
        )
    return out


# ── Сухий прогін з «набору даних» (dict), однаковий для БД і для JSON-вивантаження ──

def _dt(v):
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def dataset_responsible(dataset, cal: WorkCalendar):
    """Функція відповідального для replay() за історичними даними:
    власник клієнта / останній менеджер / хто був на зміні в момент пропуску (з черги)."""
    contacts = {int(k): v for k, v in (dataset.get("contacts") or {}).items()}
    sessions = [(int(u), _dt(s), _dt(e) if e else None) for u, s, e in (dataset.get("sessions") or [])]
    queue = [int(u) for u in (dataset.get("queue") or [])]
    active = {int(u) for u in (dataset.get("active_ids") or [])}

    def fn(n9, ts, call, open_items):
        info = contacts.get(int(call.get("contact_id") or 0)) or {}
        on = {u for u, s, e in sessions if s <= ts and (e is None or ts < e)}
        duty = [u for u in queue if u in on]
        counts = {}
        for it in open_items:
            if it.assignee_id:
                counts[it.assignee_id] = counts.get(it.assignee_id, 0) + 1
        return choose_responsible(info.get("owner"), info.get("last"), duty, counts, active)
    return fn


def run_dataset(dataset, cal: WorkCalendar, sla_minutes=15, escalate_minutes=60):
    """Прогін набору даних → (items, звіт). Нічого не пише."""
    calls = []
    for c in dataset.get("calls") or []:
        c = dict(c)
        c["ts"] = _dt(c["ts"])
        calls.append(c)
    now = _dt(dataset["now"]) if dataset.get("now") else datetime.now(ZoneInfo(cal.tz))
    since = _dt(dataset["since"]) if dataset.get("since") else None
    items = replay(calls, cal, sla_minutes, dataset.get("ignore") or (), dataset_responsible(dataset, cal))
    if since is not None:
        items = [it for it in items if it.first_missed_at >= since]
    users = {int(k): v for k, v in (dataset.get("users") or {}).items()}
    report = {"total": stats(items, cal, now, escalate_minutes), "by_manager": [], "by_line": [], "by_reason": {}}
    groups = {}
    for it in items:
        groups.setdefault(it.assignee_id, []).append(it)
        report["by_reason"][it.assign_reason or "none"] = report["by_reason"].get(it.assign_reason or "none", 0) + 1
    for uid, lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        row = stats(lst, cal, now, escalate_minutes)
        row["name"] = users.get(uid, "Не призначено") if uid else "Не призначено"
        report["by_manager"].append(row)
    lines = {}
    for it in items:
        lines.setdefault(it.line_key, []).append(it)
    for _k, lst in sorted(lines.items(), key=lambda kv: -len(kv[1])):
        row = stats(lst, cal, now, escalate_minutes)
        row["line"] = lst[-1].line or "—"
        report["by_line"].append(row)
    return items, report
