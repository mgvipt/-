"""Крон-синк аналітики TikTok (і комент-поллер прямого каналу).

  manage.py tiktok_sync --daily --videos   # щоночі: добові метрики + метрики відео
  manage.py tiktok_sync --comments         # кожні 5 хв: нові коментарі → Чати CRM
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Синк аналітики TikTok та коментарів у Чати"

    def add_arguments(self, parser):
        parser.add_argument("--daily", action="store_true")
        parser.add_argument("--videos", action="store_true")
        parser.add_argument("--comments", action="store_true")
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **opts):
        from apps.tiktok_insights import service
        if opts["daily"]:
            self.stdout.write("daily: %s" % service.sync_daily(opts["days"]))
        if opts["videos"]:
            self.stdout.write("videos: %s" % service.sync_videos(200))
        if opts["comments"]:
            from apps.inbox import tiktok as tt
            self.stdout.write("comments: %s" % tt.poll_comments())
        if not (opts["daily"] or opts["videos"] or opts["comments"]):
            self.stdout.write("нічого не вибрано: --daily/--videos/--comments")
