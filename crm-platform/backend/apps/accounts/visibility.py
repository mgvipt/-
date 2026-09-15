"""Де показувати звільнених співробітників (staffvis, 15.09.2026).

Олег: «у прорахунках ЗП/KPI у списку багато співробітників, які вже не працюють… у вкладці Звільнені мають бути
налаштування: кого показувати в яких сутностях, і щоб вони, якщо їх відключаєш, не потрапляли в аналітику
і в точку беззбитковості».

ОДНЕ правило на всю CRM:
- Активні й неактивні (відпустка/пауза) — нічого не змінюється, ця логіка їх не чіпає.
- Звільнений (employment_status="dismissed") — для кожної сутності власник обирає:
    «Показувати» (True) · «Приховати» (False) · нічого не обрано = «Авто».
  «Авто»: у звіті за місяць/період людина видна, лише якщо в цьому періоді ще працювала
  (дата звільнення ≥ початок періоду) — щоб розрахунок останнього місяця не загубився.
  Дата звільнення невідома (старі акаунти з Бітрикса) → «Авто» = приховано.
  Точка беззбитковості — план на майбутнє, тому там «Авто» = НЕ рахувати.
  Без періоду (списки «зараз», топ за весь час) «Авто» = приховано.
- Затверджені відомості ЗП, привʼязані виплати, журнал грошей — історія: цей модуль їх не ховає і не змінює.

Зберігання — без міграції: IntegrationSettings(provider="staff_visibility").config =
  {"users": {"<id>": {"payroll": false, ...}}, "meta": {"<id>": {"by": "Олег", "at": "...ISO..."}}}
Зміна — лише переданих сутностей однієї людини під select_for_update: новіші налаштування інших людей
і інших сутностей не затираються.
"""
import logging
from datetime import date, datetime

log = logging.getLogger(__name__)

PROVIDER = "staff_visibility"
# (ключ, назва для власника, де це в CRM)
ENTITIES = [
    ("payroll", "ЗП і KPI", "Фінанси → ЗП/KPI: розрахунок за ставками і стара формула"),
    ("breakeven", "Точка беззбитковості (ФОТ)", "Фінанси → Точка беззбитковості: «ФОТ за ставками» і фонди «Автоматично зі Ставок»"),
    ("plans", "Плани продажів", "Фінанси → Плани"),
    ("sales_analytics", "Аналітика продажів", "Аналітика: дії менеджерів, статуси, розбір тижня, топ менеджерів"),
    ("staff_analytics", "Аналітика співробітників", "Співробітники → Активність (фільтри «Всі» і «Звільнені»)"),
    ("telephony", "Телефонія і звіти", "Пропущені дзвінки → звіт по відповідальних"),
    ("timesheet", "Табель", "Фінанси → Табель: список людей"),
]
ENTITY_KEYS = tuple(k for k, _label, _where in ENTITIES)
NO_AUTO = frozenset({"breakeven"})  # «Авто» = не рахувати ніколи (план на майбутнє)
AUTO_DEFAULT = "лише за місяці, коли ще працював(ла)"
AUTO_TEXT = {"breakeven": "не рахується"}
LABELS = {k: label for k, label, _w in ENTITIES}


def valid_choice(v):
    """Лише true / false / null (null = «Авто»). 0/1 і рядки не приймаємо."""
    return v is None or isinstance(v, bool)


def period_start(period):
    """Початок періоду звіту: «YYYY-MM» → 1-ше число; «YYYY-MM-DD» / date → ця дата; (d1, d2) → d1; None → None."""
    if period is None or period == "":
        return None
    if isinstance(period, (tuple, list)):
        return period_start(period[0]) if period else None
    if isinstance(period, datetime):
        return period.date()
    if isinstance(period, date):
        return period
    s = str(period).strip()
    try:
        if len(s) == 7:
            return date(int(s[:4]), int(s[5:7]), 1)
        return date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def _config():
    try:
        from apps.integrations.models import IntegrationSettings
        row = IntegrationSettings.objects.filter(provider=PROVIDER).first()
    except Exception:  # noqa: BLE001 — збій читання не має ламати звіти: звільнені лишаються на «Авто»
        log.exception("staff_visibility: не вдалося прочитати налаштування")
        return {}
    cfg = (row.config if row else None) or {}
    return cfg if isinstance(cfg, dict) else {}


def load():
    """{"<id>": {сутність: bool}} — лише явні вибори власника."""
    users = _config().get("users") or {}
    return users if isinstance(users, dict) else {}


def load_meta():
    meta = _config().get("meta") or {}
    return meta if isinstance(meta, dict) else {}


def choice(cfg, uid, entity):
    row = cfg.get(str(uid))
    v = row.get(entity) if isinstance(row, dict) else None
    return v if isinstance(v, bool) else None


def auto_visible(entity, dismissed_at, start):
    if entity in NO_AUTO or start is None or dismissed_at is None:
        return False
    return dismissed_at >= start


def _visible(cfg, uid, dismissed_at, entity, start):
    ch = choice(cfg, uid, entity)
    return ch if ch is not None else auto_visible(entity, dismissed_at, start)


def is_visible(user, entity, period=None, cfg=None):
    """Чи показувати людину в сутності entity за період period. Не звільнений → завжди True."""
    if user is None or getattr(user, "employment_status", "active") != "dismissed":
        return True
    if entity not in ENTITY_KEYS:
        return True
    cfg = load() if cfg is None else cfg
    return _visible(cfg, user.id, getattr(user, "dismissed_at", None), entity, period_start(period))


def _dismissed():
    from apps.accounts.models import User
    return list(User.objects.filter(employment_status="dismissed").values_list("id", "dismissed_at"))


def hidden_ids(entity, period=None):
    """id звільнених, яких НЕ показуємо в entity за період. Для невідомої сутності — порожньо (нічого не ховаємо)."""
    if entity not in ENTITY_KEYS:
        log.warning("staff_visibility: невідома сутність %r — нічого не приховую", entity)
        return set()
    cfg, start = load(), period_start(period)
    return {uid for uid, da in _dismissed() if not _visible(cfg, uid, da, entity, start)}


def visible_dismissed_ids(entity, period=None):
    """id звільнених, яких показуємо в entity за період (для списків «активні + дозволені звільнені»)."""
    if entity not in ENTITY_KEYS:
        return set()
    cfg, start = load(), period_start(period)
    return {uid for uid, da in _dismissed() if _visible(cfg, uid, da, entity, start)}


def filter_users(users, entity, period=None):
    """Список/QuerySet людей → список без прихованих звільнених (порядок зберігається)."""
    hid = hidden_ids(entity, period)
    return [u for u in users if getattr(u, "id", None) not in hid] if hid else list(users)


def _who(u):
    if u is None:
        return ""
    return ((getattr(u, "first_name", "") or "") + " " + (getattr(u, "last_name", "") or "")).strip() or getattr(u, "username", "")


def describe(choices):
    """{"payroll": False} → «ЗП і KPI: приховати» (для журналу дій)."""
    parts = ["%s: %s" % (LABELS[k], "показувати" if v else "приховати")
             for k, v in (choices or {}).items() if k in LABELS and isinstance(v, bool)]
    return ", ".join(parts) or "усе «Авто»"


def save_choices(user_id, changes, by=None):
    """changes: {сутність: True | False | None}; None → «Авто». Змінюються ЛИШЕ передані сутності цієї людини.
    Повертає (було, стало) для журналу."""
    from django.db import transaction
    from django.utils import timezone
    from apps.integrations.models import IntegrationSettings
    clean = {k: v for k, v in (changes or {}).items() if k in ENTITY_KEYS and valid_choice(v)}
    IntegrationSettings.objects.get_or_create(provider=PROVIDER, defaults={"config": {}, "is_active": True})
    key = str(int(user_id))
    with transaction.atomic():
        row = IntegrationSettings.objects.select_for_update().get(provider=PROVIDER)
        cfg = dict(row.config or {}) if isinstance(row.config, dict) else {}
        users = dict(cfg.get("users") or {})
        before = dict(users.get(key) or {})
        cur = dict(before)
        for k, v in clean.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        if cur:
            users[key] = cur
        else:
            users.pop(key, None)
        cfg["users"] = users
        if cur != before:
            meta = dict(cfg.get("meta") or {})
            meta[key] = {"by": _who(by), "at": timezone.now().isoformat()}
            cfg["meta"] = meta
        row.config = cfg
        row.save(update_fields=["config", "updated_at"])
    return before, cur


def entities_json():
    return [{"key": k, "label": label, "where": where, "auto": AUTO_TEXT.get(k, AUTO_DEFAULT)} for k, label, where in ENTITIES]


def hints_for(ids, today=None):
    """Підказки власнику: угоди за людиною, діюча ставка (іде у ФОТ, лише якщо дозволено), затверджені відомості."""
    from django.db.models import Count, Q
    from django.utils import timezone
    today = today or timezone.localdate()
    out = {i: {"deals": 0, "active_schemes": 0, "approved_runs": 0} for i in ids}
    if not ids:
        return out
    try:
        from apps.crm.models import Deal
        for r in Deal.objects.filter(owner_id__in=ids).values("owner_id").annotate(n=Count("id")):
            out[r["owner_id"]]["deals"] = r["n"]
    except Exception:  # noqa: BLE001 — підказка, не критично
        log.exception("staff_visibility: угоди для підказки")
    try:
        from apps.payroll.models import PayrollRun, PayScheme
        for r in (PayScheme.objects.filter(user_id__in=ids, purpose="official", status="active", is_vacancy=False,
                                           valid_from__lte=today)
                  .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).values("user_id").annotate(n=Count("id"))):
            out[r["user_id"]]["active_schemes"] = r["n"]
        for r in PayrollRun.objects.filter(user_id__in=ids, status="approved").values("user_id").annotate(n=Count("id")):
            out[r["user_id"]]["approved_runs"] = r["n"]
    except Exception:  # noqa: BLE001 — застосунку ЗП може не бути
        log.exception("staff_visibility: ставки/відомості для підказки")
    return out


def person_json(u, cfg=None, meta=None, today=None, hints=None):
    from django.utils import timezone
    cfg = load() if cfg is None else cfg
    meta = load_meta() if meta is None else meta
    today = today or timezone.localdate()
    start = today.replace(day=1)
    m = meta.get(str(u.id)) or {}
    out = {"id": u.id, "full_name": _who(u), "dismissed_at": u.dismissed_at.isoformat() if u.dismissed_at else None,
           "from_bitrix": (u.username or "").startswith("b24_"),
           "settings": {k: choice(cfg, u.id, k) for k in ENTITY_KEYS},
           "now": {k: _visible(cfg, u.id, u.dismissed_at, k, start) for k in ENTITY_KEYS},
           "changed_by": m.get("by") or "", "changed_at": m.get("at")}
    out.update(hints if hints is not None else hints_for([u.id], today).get(u.id, {}))
    return out


def overview(today=None):
    """Вкладка «Звільнені»: сутності + кожен звільнений з вибором, «зараз видно/ні» і підказками."""
    from django.db.models import F
    from django.utils import timezone
    from apps.accounts.models import User
    today = today or timezone.localdate()
    cfg, meta = load(), load_meta()
    users = list(User.objects.filter(employment_status="dismissed", account_kind="staff")
                 .order_by(F("dismissed_at").desc(nulls_last=True), "first_name", "last_name", "username"))
    hints = hints_for([u.id for u in users], today)
    return {"entities": entities_json(), "month": today.strftime("%Y-%m"),
            "people": [person_json(u, cfg, meta, today, hints.get(u.id)) for u in users]}
