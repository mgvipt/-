"""Імпорт історії робочої групи з РОП-бота (Hetzner bot.db → topic_history, вивантажено в JSON).

За замовчуванням — сухий прогін (нічого не пише). --limit N — записати лише перші N. --live — записати все.
Повторний запуск не дублює (ключ: чат + номер повідомлення). Голосові отримують file_id РОП-бота
і розшифруються кроном assistant_transcribe (у межах місячного ліміту асистента).
"""
import json
from datetime import datetime, timezone as dt_tz

from django.core.management.base import BaseCommand

from apps.assistant.models import AssistantChat, AssistantMessage, AssistantSettings

KINDS = {"voice": "voice", "audio": "voice", "video_note": "video_note", "photo": "photo", "document": "document"}


class Command(BaseCommand):
    help = "Імпорт історії робочої групи (JSON з topic_history РОП-бота) в особистого асистента."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--title", default="Робоча група")
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, file, title, live, limit, **kw):
        rows = json.load(open(file))
        owner = AssistantSettings.get().owner_tg_id
        if limit:
            rows = rows[:limit]
        by_kind, owner_n, have = {}, 0, 0
        for r in rows:
            k = KINDS.get(r.get("media_type") or "", "text" if r.get("text") else "other")
            by_kind[k] = by_kind.get(k, 0) + 1
            owner_n += bool(r.get("role") == "oleg" or (owner and r.get("user_id") == owner))
        chat = AssistantChat.objects.filter(chat_id=rows[0]["chat_id"]).first() if rows else None
        if chat:
            have = chat.messages.filter(message_id__in=[r["msg_id"] for r in rows]).count()
        state = "є" if chat else "новий"
        self.stdout.write(f"рядків {len(rows)} · від Олега {owner_n} · за типом {by_kind} · уже є {have} · чат {state}")
        if not live:
            self.stdout.write("СУХИЙ ПРОГІН — нічого не записано. Для запису: --limit 2 --live, потім --live.")
            return
        if not chat:
            chat = AssistantChat.objects.create(chat_id=rows[0]["chat_id"], title=title[:200],
                                                kind=AssistantChat.Kind.GROUP, enabled=True)
        made = 0
        for r in rows:
            k = KINDS.get(r.get("media_type") or "", "text" if r.get("text") else "other")
            _, created = AssistantMessage.objects.get_or_create(chat=chat, message_id=r["msg_id"], defaults={
                "from_owner": bool(r.get("role") == "oleg" or (owner and r.get("user_id") == owner)),
                "author": (r.get("first_name") or r.get("username") or "")[:160], "sender_id": r.get("user_id"),
                "kind": k, "text": (r.get("text") or "")[:8000],
                "file_id": r.get("media_file_id") or "" if k in ("voice", "video_note", "photo", "document") else "",
                "sent_at": datetime.fromtimestamp(r["ts"], tz=dt_tz.utc)})
            made += created
        self.stdout.write(f"записано нових {made}")
