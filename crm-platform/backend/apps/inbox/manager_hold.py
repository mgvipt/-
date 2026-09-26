# -*- coding: utf-8 -*-
"""«Менеджер узяв діалог» — клієнт бачить, що з його запитом уже працюють (Олег, 23.09.2026).

Чому саме так (дані CRM за 120 днів, 3 811 діалогів): відповідь до 15 хв — 17,5% оплат,
після години — 4-5%. Повідомлення не замінює швидкість, воно лише утримує клієнта, поки менеджер
іде до відповіді. Тому:
  • кнопки немає — CRM робить це сама (кнопку менеджери не натискатимуть);
  • пишемо ЛИШЕ коли клієнт реально чекає: менеджер закріпив чат і за 1-2 хвилини нічого не написав;
  • якщо менеджер відповів одразу — не пишемо нічого;
  • другий випадок: чат уже закріплений, клієнт написав і чекає довше N хвилин, а менеджер мовчить
    (типово: збирає інформацію на прорахунок) — тоді теж одне повідомлення;
  • не частіше одного разу на добу на діалог, щоб не було «хто зайшов у чат» по колу;
  • вночі не пишемо — там відповідає ШІ.
Повідомлення йде ВІД МЕНЕДЖЕРА (з його імʼям), тому ШІ в цьому чаті теж замовкає, як і має бути.
"""
import re
from datetime import timedelta

from django.utils import timezone

MARK = "авто «взяв у роботу»"          # службова позначка в чаті, щоб не писати двічі
TAKE_ACTION = "Взяв чат"


def settings_row():
    from .models import ManagerHoldSettings
    return ManagerHoldSettings.get()


def _name(user):
    if not user:
        return ""
    full = (user.get_full_name() or "").strip()
    return (full.split()[0] if full else (user.username or "")).strip()


def _work_time(now, cfg):
    return cfg.work_from <= now.time() <= cfg.work_to


def _already_sent(conv, hours):
    from .models import Message
    return Message.objects.filter(conversation=conv, internal=True, text__contains=MARK,
                                  created_at__gte=timezone.now() - timedelta(hours=hours)).exists()


def _last_in(conv):
    from .models import Message
    return Message.objects.filter(conversation=conv, direction="in", internal=False).order_by("-id").first()


def _manager_wrote_at_all(conv, hours=24):
    """Менеджер уже писав у цьому чаті — значить, він у розмові, і знайомство не потрібне."""
    from .models import Message
    return Message.objects.filter(conversation=conv, direction="out", internal=False, sender__isnull=False,
                                  created_at__gte=timezone.now() - timedelta(hours=hours)).exists()


def _anyone_wrote_after(conv, when):
    """Чи хтось із нашого боку вже відповів на це повідомлення клієнта — менеджер АБО ШІ.
    26.09.2026: раніше дивились лише на живих менеджерів, тому після відповіді ШІ клієнт
    отримував ще й «збираю для вас інформацію» — і це виглядало недоречно."""
    from .models import Message
    return Message.objects.filter(conversation=conv, direction="out", internal=False,
                                  created_at__gt=when).exists()


def _already_sent_contact(conv, hours):
    """Одна людина = одне повідомлення на добу, навіть якщо в неї кілька чатів
    (Instagram + архів ChatPlace тощо)."""
    from .models import Message
    if not conv.contact_id:
        return _already_sent(conv, hours)
    return Message.objects.filter(conversation__contact_id=conv.contact_id, internal=True,
                                  text__contains=MARK,
                                  created_at__gte=timezone.now() - timedelta(hours=hours)).exists()


def _manager_wrote_after(conv, when):
    from .models import Message
    return Message.objects.filter(conversation=conv, direction="out", internal=False, sender__isnull=False,
                                  created_at__gt=when).exists()


def _took_at(conv):
    """Коли менеджер закріпив цей чат за собою (лог «Взяв чат» по клієнту)."""
    from apps.crm.models import ActivityLog
    if not conv.contact_id:
        return None
    row = (ActivityLog.objects.filter(kind="contact", object_id=conv.contact_id, action=TAKE_ACTION)
           .order_by("-id").values("created_at", "user_id").first())
    return row


def text_for(conv, cfg, waiting=False):
    who = _name(conv.assigned_to)
    tpl = cfg.text_waiting if waiting else cfg.text_take
    deadline = (timezone.localtime() + timedelta(minutes=cfg.promise_minutes)).strftime("%H:%M")
    return tpl.replace("{менеджер}", who or "менеджер").replace("{час}", deadline)


def candidates(now=None):
    """Пари (чат, «чекає давно»?), яким зараз треба надіслати повідомлення."""
    from .models import Conversation
    cfg = settings_row()
    if not cfg.enabled:
        return []
    now = now or timezone.localtime()
    if not _work_time(now, cfg):
        return []
    out = []
    qs = (Conversation.objects.filter(status="open", assigned_to__isnull=False)
          .select_related("assigned_to", "channel", "contact").order_by("-last_message_at")[:400])
    for conv in qs:
        if str(conv.external_chat_id or "").startswith("comment:"):
            continue                                   # коментарі під постами — не особистий чат, туди не пишемо
        inc = _last_in(conv)
        if inc is None:
            continue                                   # клієнт нічого не писав — нічого й не тримаємо
        if _anyone_wrote_after(conv, inc.created_at):
            continue                                   # на останнє повідомлення вже відповіли (менеджер або ШІ)
        if _manager_wrote_at_all(conv):
            continue                                   # менеджер уже в розмові — знайомство недоречне
        if _already_sent_contact(conv, cfg.per_dialog_hours):
            continue
        waited = (timezone.now() - inc.created_at).total_seconds()
        took = _took_at(conv)
        just_took = bool(took and took["user_id"] == conv.assigned_to_id
                         and (timezone.now() - took["created_at"]).total_seconds() <= cfg.take_window_sec
                         and (timezone.now() - took["created_at"]).total_seconds() >= cfg.delay_sec)
        if just_took:
            out.append((conv, False))
        elif cfg.wait_minutes * 60 <= waited <= cfg.max_wait_hours * 3600:
            out.append((conv, True))   # чекає, але недовго: по старих діалогах не пишемо (це вже не «щойно»)
    return out


def send(conv, waiting, cfg=None, dry=False):
    from .models import Message
    from .services import send_message
    cfg = cfg or settings_row()
    text = text_for(conv, cfg, waiting)
    if dry:
        return text
    msg = send_message(conv, text, user=conv.assigned_to)
    Message.objects.create(conversation=conv, direction="out", internal=True,
                           text="%s: %s (%s)" % (MARK, "клієнт чекав" if waiting else "щойно взяв чат",
                                                 _name(conv.assigned_to)),
                           sender_name="CRM")
    return msg


def sweep(dry=False, limit=50):
    rows = candidates()[:limit]
    done = []
    for conv, waiting in rows:
        try:
            r = send(conv, waiting, dry=dry)
            done.append((conv.id, "чекав" if waiting else "взяв", r if dry else "надіслано"))
        except Exception as e:
            done.append((conv.id, "помилка", str(e)[:120]))
    return done
