"""Крон ~5 хв: фоновий РОП проставляє бейдж приоритету новим/оновленим чатам.
Аналізує до CAP чатів за прогін (контроль токенів), повторно лише коли зʼявились нові повідомлення."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.inbox.models import Conversation, Message
from apps.crm.priority import classify

CAP = 30


class Command(BaseCommand):
    help = "Фоновий РОП: проставити бейдж приоритету (возмущение/просчёт/срочно/...) новим чатам"

    def handle(self, *args, **opts):
        from apps.crm.models import AgentConfig
        if not AgentConfig.get().priority_enabled:
            self.stdout.write("priority_sweep: вимкнено в налаштуваннях"); return
        done = 0
        convs = Conversation.objects.filter(status="open").order_by("-last_message_at")
        for conv in convs.iterator():
            if done >= CAP:
                break
            msgs = list(Message.objects.filter(conversation=conv).order_by("created_at").values("direction", "text"))
            cnt = len(msgs)
            if cnt == 0:
                continue
            # вже аналізували і нових повідомлень нема → пропустити
            if conv.priority_at and conv.priority_seen_count >= cnt:
                continue
            if not any(m["direction"] == "in" for m in msgs):
                conv.priority_seen_count = cnt
                conv.save(update_fields=["priority_seen_count"])
                continue
            tag, reason = classify(msgs)
            conv.priority = tag
            conv.priority_reason = reason
            conv.priority_at = timezone.now()
            conv.priority_seen_count = cnt
            conv.save(update_fields=["priority", "priority_reason", "priority_at", "priority_seen_count"])
            done += 1
        self.stdout.write(f"priority_sweep: проаналізовано {done} чатів")
