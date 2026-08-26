"""Юля: режим залежно від змін менеджерів продажу — V4 (14.08.2026).

Правило Олега (14.08.2026):
- «Відповідати в Direct» (answerOnMessageEnabled) — ЗАВЖДИ УВІМКНЕНО. Юля НІКОЛИ не вимикається повністю.
- Перемикаємо ТІЛЬКИ «Відключатися при вашій відповіді» (silenceAfterHumanReplyEnabled; пауза 600 хв = 10 год):
  * >=1 sales-менеджер на зміні (день начат, не на паузі) → silenceAfterHumanReplyEnabled = TRUE
      → Юля відповідає ТІЛЬКИ на нетронуті чати, і то через 10 год мовчання (менеджери ведуть самі).
  * 0 активних (усі на паузі / день закрито) → silenceAfterHumanReplyEnabled = FALSE
      → Юля відповідає ВСІМ одразу (повний автопілот, людей немає).
- Тригер — hook у WorkTimeView.post після start/pause/stop.
- При зміні режиму — TG-нотифікація + БД-мітка для бейджа.

INVARIANTS -- NE LAMATY pry hlobalnyh perevirkah/refaktori (rehlament Oleha 22.08):
1. "Aktyvnyy" = vede kliyentiv = viddil mistyt "Prodazh" ABO "Kerivn"(ytstvo) ABO user.is_superuser.
   Sklad/Lohistyka/Vyrobnytstvo NE rahuyutsya. Tse v 3 mistsyah, VSI musyat buty odnakovi:
   (a) _active_sales_managers() tut; (b) _yulia_hook_after_shift_action() u finance/views.py
   (guard na start/pauzu/stop zminy); (c) sweep_worktime.py -- zve apply_yulia_shift_toggle()
   u kintsi (kron */3) dlya SVERKY, bo avto-pauza/avto-zakryttya zminy ydut povz hook.
   Yakshcho des lyshyty tilky "Prodazh" -- stan Yuli dreyfuye (Oleh/Kerivnytstvo ne tryheryt).
2. answerOnMessageEnabled -- ZAVZHDY True (Yulya nikoly povnistyu ne vymykayetsya).
3. apply_yulia_shift_toggle() bez force chipaye ChatPlace LYShE koly want != zberezhenyy stan
   (stabilno = 0 zayvyh zapytiv; sweep mozhe zvaty shchohvylyny bezpechno).
"""
import logging
import json
import urllib.request
from django.conf import settings

log = logging.getLogger(__name__)

YULIA_IG_BOT_ID = "647e28e9-73fd-4f06-81cc-5970409a7381"
YULIA_TT_BOT_ID = "4aab5db8-4efa-46aa-a0bf-56fc20610b35"
SALES_DEPARTMENT_NAME_ICONTAINS = "Продаж"
SILENCE_MINUTES = 600  # 10 годин — пауза Юлі після відповіді менеджера


def _active_sales_managers():
    """На зміні і НЕ на паузі — ті, хто веде клієнтів: відділ Продаж АБО Керівництво,
    АБО власник (superuser). Склад/Логістика/Виробництво НЕ рахуються (не відповідають
    клієнтам). Якщо хтось із них на зміні → Юля в тихому режимі (менеджери ведуть самі)."""
    from django.db.models import Q
    from apps.finance.models import WorkSession
    qs = WorkSession.objects.filter(
        ended_at__isnull=True,
        paused_at__isnull=True,
        user__is_active=True,
    ).filter(
        Q(user__department__name__icontains=SALES_DEPARTMENT_NAME_ICONTAINS)
        | Q(user__department__name__icontains="Керівн")
        | Q(user__is_superuser=True)
    ).select_related("user")
    return [ws.user for ws in qs]


def _get_state():
    """Збережений режим: yulia_silence_on (True = тихий режим, менеджери на зміні)."""
    from apps.inbox.models import Channel
    ch = Channel.objects.filter(config__chatplace=True).first()
    return bool((ch.config or {}).get("yulia_silence_on", True)) if ch else True


def _set_state(silence_on: bool):
    from apps.inbox.models import Channel
    for ch in Channel.objects.filter(config__chatplace=True):
        cfg = dict(ch.config or {})
        cfg["yulia_silence_on"] = bool(silence_on)
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


def _cp_update(bot_id, silence_on):
    """«Відповідати в Direct» ЗАВЖДИ true; перемикаємо тільки паузу після відповіді менеджера."""
    from apps.inbox.chatplace import _mcp
    args = {
        "botId": bot_id,
        "answerOnMessageEnabled": True,                     # відповіді в Direct — ЗАВЖДИ УВІМКНЕНІ
        "silenceAfterHumanReplyEnabled": bool(silence_on),  # пауза після відповіді менеджера (тихий режим)
        "silenceAfterHumanReply": SILENCE_MINUTES,          # 10 годин
    }
    try:
        return _mcp("ai_agent_update_settings", args)
    except Exception as e:
        log.warning(f"ChatPlace update failed for bot {bot_id}: {e}")
        return None


def _check(r, silence_on):
    if not r:
        return False
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except Exception:
            return False
    if not isinstance(r, dict):
        return False
    return (bool(r.get("silenceAfterHumanReplyEnabled")) == bool(silence_on)
            and bool(r.get("answerOnMessageEnabled")) is True)


def apply_yulia_shift_toggle(force=False):
    """Викликається з shift start/pause/stop.

    Правило:
    - active_n >= 1 → silence_on = True  (тихий режим: тільки нетронуті чати через 10 год)
    - active_n == 0 → silence_on = False (Юля відповідає всім одразу)
    force=True — застосувати навіть якщо режим не змінився (для першого синку/міграції).
    """
    managers = _active_sales_managers()
    active_n = len(managers)
    want_silence_on = active_n >= 1
    prev = _get_state()

    result = {
        "silence_on": want_silence_on,
        "answer_in_direct": True,
        "active_count": active_n,
        "active_managers": [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in managers],
    }

    if want_silence_on == prev and not force:
        result["changed"] = False
        return result

    r_ig = _cp_update(YULIA_IG_BOT_ID, want_silence_on)
    r_tt = _cp_update(YULIA_TT_BOT_ID, want_silence_on)

    _set_state(want_silence_on)
    result["changed"] = True
    result["chatplace_ig_ok"] = _check(r_ig, want_silence_on)
    result["chatplace_tt_ok"] = _check(r_tt, want_silence_on)

    if want_silence_on:
        names = ", ".join(m["name"] for m in result["active_managers"]) or "?"
        _tg_notify(f"🔵 <b>Юля — тихий режим</b>\nНа зміні: {names}\nЮля відповідає в Direct ТІЛЬКИ на нетронуті чати (через 10 год мовчання). Менеджери ведуть діалоги самі.")
    else:
        _tg_notify("🟢 <b>Юля відповідає всім</b>\nУсі менеджери на паузі / завершили день.\nЮля веде клієнтів у Direct сама, без 10-год паузи.")

    log.info(f"Yulia shift toggle V4: active={active_n}, silence_on={want_silence_on}, IG={result['chatplace_ig_ok']}, TT={result['chatplace_tt_ok']}")
    return result


def yulia_status():
    """Поточний режим без змін (GET /api/yulia/status/)."""
    managers = _active_sales_managers()
    silence_on = _get_state()
    return {
        "answer_in_direct": True,      # завжди
        "silence_on": silence_on,      # тихий режим (менеджери на зміні)
        "active_count": len(managers),
        "active_managers": [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in managers],
        "agent_on": (not silence_on),  # back-compat: «відповідає всім» коли silence off
    }
