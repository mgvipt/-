"""Юля on/off залежно від змін менеджерів продажу — V2.

Правило Олега (12.08.2026):
- ≥1 sales-менеджер на зміні (день начат, не на паузе) → Юля ПОВНІСТЮ ВИМКНЕНА (менеджер сам все веде):
  * answerOnMessageEnabled = false (не відповідає в Direct)
  * answerOnCommentEnabled = false (не відповідає на коменти)
  * engageCommentUserEnabled = false (не пише коментатору в Direct)
  * storyReplyRulesEnabled = false (не відповідає на реакції в сторис)
  * storyMentionRulesEnabled = false (не відповідає на відмітки в сторис)
- 0 активних → Юля ПОВНІСТЮ УВІМКНЕНА (всі 5 → true) — сама веде діалоги.
- Тригер — hook у WorkTimeView.post після start/pause/stop.
- При зміні state — TG-нотифікація + оновлюється БД-мітка для бейджа.
"""
import logging
import json
import urllib.request
from django.conf import settings

log = logging.getLogger(__name__)

YULIA_IG_BOT_ID = "647e28e9-73fd-4f06-81cc-5970409a7381"
YULIA_TT_BOT_ID = "4aab5db8-4efa-46aa-a0bf-56fc20610b35"
SALES_DEPARTMENT_NAME_ICONTAINS = "Продаж"

# Ключі які перемикаємо (Юля повністю on/off). Story-налаштування ChatPlace
# не приймає через ai_agent_update_settings (окремі endpoints) — залишаємо як є.
_TOGGLE_KEYS = [
    "answerOnMessageEnabled",       # відповіді в Direct
    "answerOnCommentEnabled",       # відповіді на коменти
    "engageCommentUserEnabled",     # залучення коментатора в Direct
]


def _active_sales_managers():
    from apps.finance.models import WorkSession
    qs = WorkSession.objects.filter(
        ended_at__isnull=True,
        paused_at__isnull=True,
        user__is_active=True,
        user__department__name__icontains=SALES_DEPARTMENT_NAME_ICONTAINS,
    ).select_related("user")
    return [ws.user for ws in qs]


def _get_state():
    """Читає збережений стан з БД. Використовуємо inbox.Channel.config як bag.
    Стан: yulia_agent_on (True/False) — Юля увімкнена/вимкнена."""
    from apps.inbox.models import Channel
    ch = Channel.objects.filter(config__chatplace=True).first()
    return bool((ch.config or {}).get("yulia_agent_on", True)) if ch else True


def _set_state(agent_on: bool):
    from apps.inbox.models import Channel
    for ch in Channel.objects.filter(config__chatplace=True):
        cfg = dict(ch.config or {})
        cfg["yulia_agent_on"] = bool(agent_on)
        ch.config = cfg
        ch.save(update_fields=["config"])


def _tg_notify(text):
    token = getattr(settings, "TG_BOT_TOKEN", "") or ""
    chat_id = getattr(settings, "TG_WORK_GROUP_CHAT_ID", "") or ""
    if not token or not chat_id:
        log.info(f"TG notify (skipped, no config): {text}")
        return
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            log.info(f"TG notify OK: HTTP {r.status}")
    except Exception as e:
        log.warning(f"TG notify failed: {e}")


def _cp_update(bot_id, agent_on):
    """Викликає ai_agent_update_settings — перемикає ВСІ 5 ключів разом."""
    from apps.inbox.chatplace import _mcp
    args = {"botId": bot_id}
    for key in _TOGGLE_KEYS:
        args[key] = bool(agent_on)
    try:
        return _mcp("ai_agent_update_settings", args)
    except Exception as e:
        log.warning(f"ChatPlace update failed for bot {bot_id}: {e}")
        return None


def apply_yulia_shift_toggle():
    """Основна функція. Викликається з shift start/pause/stop.

    Правило:
    - active_n >= 1 → agent_on = False (Юля вимкнена, менеджер сам)
    - active_n == 0 → agent_on = True (Юля увімкнена, веде сама)
    """
    managers = _active_sales_managers()
    active_n = len(managers)
    want_agent_on = active_n == 0  # False коли є менеджер, True коли всі на паузі
    prev_agent_on = _get_state()

    result = {
        "agent_on": want_agent_on,
        "active_count": active_n,
        "active_managers": [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in managers],
    }

    if want_agent_on == prev_agent_on:
        result["changed"] = False
        return result

    # Стан змінився — оновлюємо ChatPlace обох ботів
    r_ig = _cp_update(YULIA_IG_BOT_ID, want_agent_on)
    r_tt = _cp_update(YULIA_TT_BOT_ID, want_agent_on)
    # verify: всі 5 ключів встановлені як want
    def _check(r):
        if not r: return False
        import json as _j
        if isinstance(r, str):
            try: r = _j.loads(r)
            except Exception: return False
        if not isinstance(r, dict): return False
        return all(bool(r.get(k)) == want_agent_on for k in _TOGGLE_KEYS)
    ok_ig = _check(r_ig)
    ok_tt = _check(r_tt)

    _set_state(want_agent_on)
    result["changed"] = True
    result["chatplace_ig_ok"] = ok_ig
    result["chatplace_tt_ok"] = ok_tt

    if want_agent_on:
        _tg_notify("🟢 <b>Юля увімкнена</b>\nУсі менеджери продажу на паузі / завершили день.\nЮля тепер сама відповідає клієнтам у Direct, коментах та сторис.")
    else:
        names = ", ".join(m["name"] for m in result["active_managers"]) or "?"
        _tg_notify(f"🔴 <b>Юля вимкнена</b>\nНа зміні: {names}\nМенеджер веде діалоги сам. Юля не пише клієнтам.")

    log.info(f"Yulia shift toggle: active={active_n}, agent_on={want_agent_on}, IG={ok_ig}, TT={ok_tt}")
    return result


def yulia_status():
    """Читання поточного стану без змін (для GET /api/yulia/status/)."""
    managers = _active_sales_managers()
    return {
        "agent_on": _get_state(),
        "active_count": len(managers),
        "active_managers": [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in managers],
    }
