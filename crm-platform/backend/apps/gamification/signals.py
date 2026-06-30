from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.crm.models import DialogAnalysis
from .xp import award_for_analysis


@receiver(post_save, sender=DialogAnalysis)
def on_analysis(sender, instance, created, **kwargs):
    try:
        award_for_analysis(instance)
    except Exception:
        pass
