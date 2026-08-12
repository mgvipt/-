"""Юля on/off залежно від змін менеджерів продажу.

Правило Олега (12.08.2026):
- Скільки менеджерів департаменту «Продажі» зараз активні (WorkSession без ended_at і без paused_at) = N.
- N >= 1 → Юля-ChatPlace замовкає при відповіді менеджера (silenceAfterHumanReplyEnabled=true).
- N == 0 → Юля сама веде діалоги без пауз (silenceAfterHumanReplyEnabled=false).
- При зміні стану — TG-нотифікація у робочу групу + оновлюється БД-мітка для бейджа у шапці CRM.

Викликається з WorkTimeView.post після start/pause/stop.
"""
import logging
import json
import urllib.request
import urllib.error
from django.conf import settings

log = logging.getLogger(__name__)

YULIA_IG_BOT_ID = "647e28e9-73fd-4f06-81cc-5970409a7381"
YULIA_TT_BOT_ID = "4aab5db8-4efa-46aa-a0bf-56fc20610b35"
YULIA_SILENCE_MINUTES = 600  # 10 годин
SALES_DEPARTMENT_NAME_ICONTAINS = "Продаж"


def _active_sales_managers():
    """Список активних (день почато, не на паузі) sales-менеджерів."""
    from apps.finance.models import WorkSession
    from django.db.models import Q
    qs = WorkSession.objects.filter(
        ended_at__isnull=True,
        paused_at__isnull=True,
        user__is_active=True,
        user__department__name__icontains=SALES_DEPARTMENT_NAME_ICONTAINS,
    ).select_related("user")
    return [ws.user for ws in qs]


def _get_state():
    """Читає збережений стан з БД (finance.Settings або кеш). Використовуємо inbox.Channel.config як bag."""
    from apps.inbox.models import Channel
    ch = Channel.objects.filter(config__chatplace=True).first()
    return bool((ch.config or {}).get("yulia_shift_enabled")) if ch else False


def _set_state(enabled: bool):
    from apps.inbox.models import Channel
    for ch in Channel.objects.filter(config__chatplace=True):
        cfg = dict(ch.config or {})
        cfg["yulia_shift_enabled"] = bool(enabled)
        ch.config = cfg
        ch.save(update_fields=["config"])


def _tg_notify(text):
    """TG-нотифікація у робочу групу. Токен+chat_id з settings (env)."""
    token = getattr(settings, "TG_BOT_TOKEN", "") or ""
    chat_id = getattr(settings, "TG_WORK_GROUP_CHAT_ID", "") or ""
    if not token or not chat_id:
        log.info(f"TG notify (skipped, no config): {text}")
        return
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            log.info(f"TG notify OK: HTTP {r.status}")
    except Exception as e:
        log.warning(f"TG notify failed: {e}")


def _cp_update(bot_id, enabled, minutes):
    """Виклик ChatPlace MCP через існуючу chatplace._mcp (з flip-flop fallback)."""
    from apps.inbox.chatplace import _mcp
    try:
        return _mcp("ai_agent_update_settings", {
            "botId": bot_id,
            "silenceAfterHumanReplyEnabled": bool(enabled),
            "silenceAfterHumanReply": int(minutes),
        })
    except Exception as e:
        log.warning(f"ChatPlace update failed for bot {bot_id}: {e}")
        return None


def apply_yulia_shift_toggle():
    """Основна функція. Викликається з shift start/pause/stop.

    Логіка:
    - active_n = скільки sales-менеджерів зараз активні
    - want_silence = (active_n >= 1) → так/ні
    - Якщо state змінився → викликати ai_agent_update_settings + TG-нотифікація + збереження state
    - Завжди повертає {enabled, active_managers: [{id, name}]} для бейджа.
    """
    managers = _active_sales_managers()
    active_n = len(managers)
    want_silence = active_n >= 1  # ≥1 → Юля замовкає коли пише менеджер (silence увімкнено)
    prev_silence = _get_state()

    result = {
        "silence_enabled": want_silence,
        "active_count": active_n,
        "active_managers": [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in managers],
    }

    if want_silence == prev_silence:
        result["changed"] = False
        return result

    # Стан змінився — оновлюємо ChatPlace обох ботів
    r_ig = _cp_update(YULIA_IG_BOT_ID, want_silence, YULIA_SILENCE_MINUTES)
    r_tt = _cp_update(YULIA_TT_BOT_ID, want_silence, YULIA_SILENCE_MINUTES)
    ok_ig = bool(r_ig and r_ig.get("silenceAfterHumanReplyEnabled") == want_silence)
    ok_tt = bool(r_tt and r_tt.get("silenceAfterHumanReplyEnabled") == want_silence)

    _set_state(want_silence)
    result["changed"] = True
    result["chatplace_ig_ok"] = ok_ig
    result["chatplace_tt_ok"] = ok_tt

    # TG-нотифікація
    if want_silence:
        names = ", ".join(m["name"] for m in result["active_managers"]) or "?"
        _tg_notify(f"🟢 <b>Юля тепер чекає менеджера</b>\nНа зміні: {names}\nКоли менеджер відповість — Юля замовкне на 10 год.")
    else:
        _tg_notify(f"🔴 <b>Юля тепер веде діалоги сама</b>\nУсі менеджери продажу на паузі / завершили день.\nЮля відповідає клієнтам без пауз.")

    log.info(f"Yulia shift toggle: active={active_n}, silence={want_silence}, IG={ok_ig}, TT={ok_tt}")
    return result


def yulia_status():
    """Читання поточного стану без змін (для GET /api/yulia/status/)."""
    managers = _active_sales_managers()
    return {
        "silence_enabled": _get_state(),
        "active_count": len(managers),
        "active_managers": [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in managers],
    }
