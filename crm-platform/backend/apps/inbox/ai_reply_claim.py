"""Cross-worker at-most-once seller execution; no SQL transaction spans network calls."""
import logging
import time
from contextlib import contextmanager
from threading import RLock

from django.conf import settings
from django.db import connection, transaction, close_old_connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime

log = logging.getLogger(__name__)
_TEST_LOCK = RLock()
LOCK_NAMESPACE = 19471001


@contextmanager
def conversation_lock(conv_id):
    if connection.vendor != "postgresql":
        if not getattr(settings, "AI_CLAIM_TEST_LOCK", False):
            raise RuntimeError("AI seller requires PostgreSQL for cross-worker locking")
        with _TEST_LOCK:
            yield
        return
    # Session-scoped lock: the same Django connection is retained until finally.
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s, %s)", [LOCK_NAMESPACE, conv_id])
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s, %s)", [LOCK_NAMESPACE, conv_id])


def set_state(conv_id, **fields):
    from .models import Conversation
    # Read/merge under a short row lock, never save a stale worker's entire config.
    with transaction.atomic():
        row = Conversation.objects.select_for_update().get(pk=conv_id)
        cfg = dict(row.config or {})
        cfg.update(fields)
        row.config = cfg
        row.save(update_fields=["config"])


def run_claimed(conv_id):
    from . import ai_reply
    from .models import Conversation, Message
    close_old_connections()
    try:
        with conversation_lock(conv_id):
            conv = Conversation.objects.select_related("channel").filter(pk=conv_id).first()
            if not conv:
                return
            cfg = conv.config or {}
            stamp = parse_datetime(cfg.get("ai_claimed_at") or "")
            if stamp:
                delay = ai_reply.MIN_SECONDS - (timezone.now() - stamp).total_seconds()
                if delay > 0:
                    time.sleep(min(delay, ai_reply.MIN_SECONDS))
            # Fast consecutive input is coalesced only after the preceding worker finishes.
            conv = Conversation.objects.select_related("channel").get(pk=conv_id)
            incoming = conv.messages.filter(direction="in", internal=False).order_by("-id").first()
            if not incoming:
                return
            cfg = conv.config or {}
            if cfg.get("ai_claim_state") == "claimed":
                ai_reply._note(conv, "ШІ у каналі: попередня спроба для повідомлення #%s перервалася. Перевірте доставку та замовлення і дайте відповідь вручну; автоматично не повторюємо." % cfg.get("ai_last_claimed_incoming_id"))
                set_state(conv_id, ai_claim_state="interrupted")
                return
            if cfg.get("ai_claim_state") in ("interrupted", "failed"):
                # Resume only after a human has inspected/responded; the normal quiet window still applies.
                if not stamp or not Message.objects.filter(conversation=conv, direction="out", internal=False,
                        sender__isnull=False, created_at__gt=stamp).exists():
                    return
            if cfg.get("ai_last_claimed_incoming_id") == incoming.pk:
                return
            if not ai_reply.should_reply(conv, incoming, short_gate=False):
                return
            set_state(conv_id, ai_last_claimed_incoming_id=incoming.pk,
                      ai_claimed_at=timezone.now().isoformat(), ai_claim_state="claimed")
            try:
                result = ai_reply._reply_once(conv_id, expected_incoming_id=incoming.pk)
                set_state(conv_id, ai_claim_state=result or "finished", ai_claim_finished_at=timezone.now().isoformat())
            except Exception:
                set_state(conv_id, ai_claim_state="failed", ai_claim_finished_at=timezone.now().isoformat())
                ai_reply._note(conv, "ШІ у каналі: спроба завершилася помилкою. Перевірте останні повідомлення і замовлення; автоматично не повторюємо.")
                log.exception("AI seller failed for conversation %s", conv_id)
    except Exception:
        log.exception("AI seller worker unavailable for conversation %s", conv_id)
    finally:
        close_old_connections()
