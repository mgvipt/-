"""Create privacy-safe Meta conversion outbox records from CRM changes."""

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Deal, Lead, Payment


def _remember_previous(instance, field):
    if not instance.pk:
        setattr(instance, f"_meta_capi_previous_{field}", None)
        return
    previous = type(instance).objects.filter(pk=instance.pk).values_list(field, flat=True).first()
    setattr(instance, f"_meta_capi_previous_{field}", previous)


@receiver(pre_save, sender=Lead)
@receiver(pre_save, sender=Deal)
def remember_stage(sender, instance, **kwargs):
    _remember_previous(instance, "stage_id")


@receiver(post_save, sender=Lead)
@receiver(post_save, sender=Deal)
def queue_stage_conversion(sender, instance, created, **kwargs):
    previous = getattr(instance, "_meta_capi_previous_stage_id", None)
    if not created and previous == instance.stage_id:
        return
    pk = instance.pk

    def _queue():
        from .meta_conversions import queue_stage_event
        entity = sender.objects.select_related("contact", "funnel", "stage__funnel").filter(pk=pk).first()
        if entity:
            queue_stage_event(entity)

    transaction.on_commit(_queue)


@receiver(pre_save, sender=Payment)
def remember_payment_status(sender, instance, **kwargs):
    _remember_previous(instance, "is_paid")


@receiver(post_save, sender=Payment)
def queue_paid_conversion(sender, instance, created, **kwargs):
    previous = getattr(instance, "_meta_capi_previous_is_paid", None)
    if not instance.is_paid or (not created and previous is True):
        return
    pk = instance.pk

    def _queue():
        from .meta_conversions import queue_payment_event
        payment = (Payment.objects.select_related("deal__contact", "deal__funnel", "deal__stage")
                   .filter(pk=pk, is_paid=True).first())
        if payment:
            queue_payment_event(payment)

    transaction.on_commit(_queue)
