"""Автопідвищення рівня партнера одразу після оплати.

Будь-який запис у журналі фінансів (надходження або повернення) по клієнту-партнеру → після коміту
перерахунок обороту. Рівень лише зростає. Помилка тут НІКОЛИ не ламає проведення оплати.
Страховка — нічна команда `partners_sweep`.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.finance.models import Transaction

log = logging.getLogger(__name__)


@receiver(post_save, sender=Transaction)
def partner_turnover_changed(sender, instance, created, **kwargs):
    if kwargs.get("raw") or instance.direction not in ("in", "out"):
        return
    deal_id, contact_id = instance.deal_id, instance.contact_id

    def _run():
        try:
            from apps.crm.models import Deal
            from .models import PartnerStatus
            from .services import recompute
            ids = set()
            if contact_id:
                ids.add(contact_id)
            if deal_id:
                cid = Deal.objects.filter(pk=deal_id).values_list("contact_id", flat=True).first()
                if cid:
                    ids.add(cid)
            for cid in PartnerStatus.objects.filter(contact_id__in=ids).values_list("contact_id", flat=True):
                recompute(cid)
        except Exception:  # оплата важливіша за партнерку
            log.exception("partners: recompute after transaction %s failed", instance.pk)

    transaction.on_commit(_run)
