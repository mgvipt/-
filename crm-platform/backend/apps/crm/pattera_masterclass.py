"""Paid PATTERA Fine travertine tutorial. No sweep, no AI, no automatic retries.

The saved GlobalRule is the switch. Claims survive transport failures: an uncertain
send must be reviewed by a manager, never retried into a customer's inbox blindly.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Contact, Deal, GlobalRule, Payment, log_activity

log = logging.getLogger(__name__)
URL = "https://youtu.be/6u671ro-GKw"
RULE_TITLE = "PATTERA Fine · Травертин: майстер-клас після підтвердженої оплати"
REPLY_TITLE = "PATTERA Fine · Класичний травертин — після оплати"
MARKER = "pattera_travertine_masterclass_v1"
PAID_STAGES = {"оплату отримано", "оплата отримано", "оплата отримана", "оплата/предоплата"}
KIT_IDS = {1654, 1655, 1656, 1657}
FINE_ID = 1639
EFFECTS = {"травертин", "класичний травертин", "travertine", "travertin", "классический травертин"}
MATERIALS = {"pattera (травертин)", "pattera fine (травертин)", "патера (травертин)", "pattera fine — травертин"}


def norm(value):
    return " ".join(str(value or "").strip().lower().split())


def has_travertine(deal):
    ids = set(deal.items.filter(quantity__gt=0).values_list("product_id", flat=True))
    if ids & KIT_IDS:
        return True
    if FINE_ID not in ids:
        return False
    q = deal.qualification or {}
    if norm(q.get("material")) in MATERIALS:
        return True
    if any(norm(q.get(k)) in EFFECTS for k in ("effect", "technique", "texture")):
        return True
    return any(norm(f.get("label")) in {"ефект", "эффект", "техніка", "техника", "фактура"}
               and norm(f.get("value")) in EFFECTS for f in (deal.card_fields or []) if isinstance(f, dict))


def eligible(deal):
    if not deal.contact_id or deal.closed_at or deal.funnel.is_archive or deal.stage.is_lost:
        return False
    if norm(deal.stage.name) not in PAID_STAGES or not has_travertine(deal):
        return False
    # A stage name, receipt screenshot or buyer's promise is not payment evidence.
    total = deal.payments.filter(is_paid=True, checkbox_return_id="").aggregate(v=Sum("amount"))["v"] or Decimal(0)
    return total > 0


def choose_chat(contact_id):
    from apps.inbox.models import Conversation
    chats = Conversation.objects.filter(contact_id=contact_id, status="open", channel__is_active=True).exclude(
        external_chat_id__startswith="comment:").exclude(external_chat_id="").select_related("channel")
    # Only a customer-initiated private conversation; choose the latest incoming,
    # not a newer outbound-only mirror. Closed Meta windows are left to a manager.
    candidates = []
    for conv in chats:
        incoming = conv.messages.filter(direction="in").order_by("-created_at").first()
        if not incoming:
            continue
        if conv.channel.kind in {"instagram", "facebook", "whatsapp", "echat_whatsapp"} and incoming.created_at < timezone.now() - timedelta(hours=24):
            continue
        candidates.append((incoming.created_at, conv.pk, conv))
    return max(candidates, key=lambda x: (x[0], x[1]))[2] if candidates else None


def attempt(deal_id):
    from apps.inbox.models import Message, QuickReply
    from apps.inbox.services import send_message
    if not GlobalRule.objects.filter(title=RULE_TITLE, enabled=True).exists():
        return "disabled"
    with transaction.atomic():
        deal = Deal.objects.select_for_update().get(pk=deal_id)
        if not eligible(deal):
            return "ineligible"
        # Serialize different deals belonging to the same customer as well.
        Contact.objects.select_for_update().get(pk=deal.contact_id)
        nd = dict(deal.np_data or {})
        if nd.get(MARKER):
            return "already_claimed"
        if Deal.objects.filter(contact_id=deal.contact_id, np_data__has_key=MARKER).exclude(pk=deal.pk).exists():
            return "already_claimed_contact"
        previous = Message.objects.filter(conversation__contact_id=deal.contact_id, direction="out", text__contains="6u671ro-GKw").exclude(status="failed").exists()
        if previous:
            return "already_shared"
        reply = QuickReply.objects.filter(title=REPLY_TITLE, category="Майстер-класи", is_active=True).first()
        if not reply or URL not in reply.text:
            return "missing_template"
        conv = choose_chat(deal.contact_id)
        if conv is None:
            log_activity("deal", deal.id, "Майстер-клас: потрібен менеджер", "Немає відкритого приватного чату або минуло вікно повідомлень. Бібліотека → Майстер-класи.")
            return "no_safe_chat"
        nd[MARKER] = {"status": "claimed", "at": timezone.now().isoformat(), "conversation_id": conv.pk}
        Deal.objects.filter(pk=deal.pk).update(np_data=nd)
        text = reply.text
    # Network is outside the DB transaction. A crash leaves a durable claim.
    try:
        msg = send_message(conv, text, user=None)
        state = {"status": msg.status, "message_id": msg.pk}
    except Exception:
        log.exception("PATTERA tutorial send uncertain for deal %s", deal_id)
        state = {"status": "review_required"}
    with transaction.atomic():
        deal = Deal.objects.select_for_update().get(pk=deal_id)
        nd = dict(deal.np_data or {})
        nd[MARKER] = dict(nd.get(MARKER) or {}, **state)
        Deal.objects.filter(pk=deal_id).update(np_data=nd)
    log_activity("deal", deal_id, "Майстер-клас PATTERA · Травертин",
                 "Прийнято каналом; перевірте статус повідомлення." if state["status"] in {"sent", "delivered", "read"}
                 else "Потрібна перевірка менеджера; автоматичного повтору немає.", actor="Автоматизація")
    return state["status"]


def safe_attempt(deal_id):
    try:
        attempt(deal_id)
    except Exception:
        # A tutorial failure must never roll back a confirmed payment.
        log.exception("PATTERA tutorial processing failed for deal %s", deal_id)


@receiver(pre_save, sender=Deal, dispatch_uid="pattera_tutorial_previous_stage")
@receiver(pre_save, sender=Payment, dispatch_uid="pattera_tutorial_previous_payment")
def remember(sender, instance, **kwargs):
    field = "stage_id" if sender is Deal else "is_paid"
    instance._tutorial_previous = sender.objects.filter(pk=instance.pk).values_list(field, flat=True).first() if instance.pk else None


@receiver(post_save, sender=Deal, dispatch_uid="pattera_tutorial_stage")
@receiver(post_save, sender=Payment, dispatch_uid="pattera_tutorial_payment")
def on_change(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    previous = getattr(instance, "_tutorial_previous", None)
    if sender is Deal:
        if previous == instance.stage_id:
            return
        deal_id = instance.pk
    else:
        if not instance.is_paid or previous is True:
            return
        deal_id = instance.deal_id
    transaction.on_commit(lambda: safe_attempt(deal_id))
