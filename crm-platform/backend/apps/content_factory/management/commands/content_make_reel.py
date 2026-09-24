"""Зібрати рилс з нарізок: python manage.py content_make_reel "Тема" --material Галатея [--markup 15]."""
from django.core.management.base import BaseCommand

from apps.content_factory.reels import make_reel, spent_month


class Command(BaseCommand):
    help = "Розмітити відео матеріалу (лише нові), написати сценарій і змонтувати рилс"

    def add_arguments(self, parser):
        parser.add_argument("topic")
        parser.add_argument("--material", required=True)
        parser.add_argument("--markup", type=int, default=15)

    def handle(self, *args, **o):
        r = make_reel(o["topic"], o["material"], markup_limit=o["markup"])
        self.stdout.write(f"Рилс #{r.id} «{r.title}» {r.duration} с; витрати місяця ${spent_month()}")
        for b in r.beats:
            self.stdout.write(f"  {b['seconds']}с | сцена {b['scene_id']} | {b['text']}")
        self.stdout.write("Підпис: " + r.caption)
