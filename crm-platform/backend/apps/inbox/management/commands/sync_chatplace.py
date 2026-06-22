from django.core.management.base import BaseCommand
from apps.inbox.chatplace import sync_chats, configured


class Command(BaseCommand):
    help = "Синхронізувати чати ChatPlace (IG Direct) у inbox CRM"

    def handle(self, *args, **opts):
        if not configured():
            self.stdout.write("CHATPLACE_API_KEY не задано — пропуск")
            return
        r = sync_chats()
        self.stdout.write(self.style.SUCCESS(f"ChatPlace sync: {r}"))
