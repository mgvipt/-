"""Record human replies, not automatic confirmations or stage changes."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import LandingSubmission, Message


@receiver(post_save, sender=Message, dispatch_uid="landing_record_human_response")
def human_response(sender, instance, created, **kwargs):
    if not created or instance.direction != "out" or instance.internal or not instance.sender_id or instance.status in {"failed", "window_risk"}:
        return
    contact_id = instance.conversation.contact_id
    if contact_id:
        LandingSubmission.objects.filter(deal__contact_id=contact_id, responded_at__isnull=True,
            created_at__lte=instance.created_at).update(responded_at=instance.created_at)
