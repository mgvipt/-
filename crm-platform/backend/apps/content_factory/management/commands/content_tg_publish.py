"""Публікація запланованих схвалених постів у @wallcovpro (контент-завод). Крон кожні 5 хв.
Немає постів, у яких настав час, — нічого не робить."""
from django.core.management.base import BaseCommand

from apps.content_factory.telegram import publish_due


class Command(BaseCommand):
    help = "Опублікувати схвалені пости, у яких настав запланований час"

    def handle(self, *args, **opts):
        done, failed = publish_due()
        if done or failed:
            self.stdout.write(f"опубліковано {done}; помилки {failed}")
