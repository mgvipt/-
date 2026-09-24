"""Щоранкова чернетка для Telegram (контент-завод, етап 2). Крон 08:10.
Вимкнено в налаштуваннях або вже є чернетка за сьогодні → нічого платного не робить."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.content_factory import telegram as tg
from apps.content_factory.models import TgPost, TgSettings


class Command(BaseCommand):
    help = "Створити одну чернетку поста для Telegram з найчастішого питання"

    def handle(self, *args, **opts):
        if not TgSettings.get().daily_drafts:
            self.stdout.write("Вимкнено — нічого не робимо")
            return
        today = timezone.localtime().date()
        if TgPost.objects.filter(created_at__date=today).exists():
            self.stdout.write("Чернетка за сьогодні вже є")
            return
        try:
            p = tg.generate()
            self.stdout.write(f"Чернетка #{p.id}: {p.title}")
        except (tg.BudgetError, ValueError) as e:
            self.stdout.write(str(e))
