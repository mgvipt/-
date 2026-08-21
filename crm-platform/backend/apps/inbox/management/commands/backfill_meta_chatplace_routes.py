"""Точна прив'язка Meta Instagram Direct до ChatPlace UUID.

За замовчуванням лише показує підсумок. Запис у Conversation.config — тільки
з --apply. Зіставлення дозволене виключно за точним Instagram username,
отриманим через chats_get; схоже ім'я саме по собі нічого не змінює.
"""
import re
from collections import defaultdict
from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.inbox.chatplace import _mcp
from apps.inbox.models import Conversation


_USERNAME = re.compile(r"^[a-z0-9._]{1,150}$", re.I)


def _username(value):
    value = str(value or "").strip().lstrip("@").strip().lower()
    return value if _USERNAME.fullmatch(value) else ""


def _contact_username(contact):
    candidates = [getattr(contact, "nickname", "")]
    for link in [getattr(contact, "social_link", ""), *(getattr(contact, "messengers", None) or [])]:
        try:
            parsed = urlparse(str(link or ""))
            if "instagram.com" in (parsed.netloc or "").lower():
                candidates.append(parsed.path.strip("/").split("/", 1)[0])
        except Exception:
            pass
    for value in candidates:
        result = _username(value)
        if result:
            return result
    return ""


def _aliases(contact, username):
    values = {
        username,
        str(getattr(contact, "first_name", "") or "").strip().lower(),
        " ".join(x for x in (
            str(getattr(contact, "first_name", "") or "").strip(),
            str(getattr(contact, "last_name", "") or "").strip(),
        ) if x).lower(),
    }
    return {x.lstrip("@").strip() for x in values if x.strip()}


class Command(BaseCommand):
    help = "Map Meta Instagram Direct conversations to exact ChatPlace chats (DRY_RUN by default)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--max-pages", type=int, default=20)
        parser.add_argument("--conversation-id", action="append", type=int, default=[])

    def handle(self, *args, **options):
        qs = (Conversation.objects.select_related("contact", "channel")
              .filter(status="open", channel__kind="instagram")
              .order_by("-last_message_at", "-id"))
        if options["conversation_id"]:
            qs = qs.filter(id__in=options["conversation_id"])
        conversations = [
            conv for conv in qs
            if (conv.channel.config or {}).get("meta")
            and not str(conv.external_chat_id or "").startswith("comment:")
        ]
        if options["limit"]:
            conversations = conversations[:max(0, options["limit"])]

        by_username = defaultdict(list)
        alias_to_usernames = defaultdict(set)
        without_username = 0
        for conv in conversations:
            username = _contact_username(conv.contact) if conv.contact_id else ""
            if not username:
                without_username += 1
                continue
            by_username[username].append(conv)
            for alias in _aliases(conv.contact, username):
                alias_to_usernames[alias].add(username)

        matches = defaultdict(set)
        inspected_details = set()
        cursor_id = None
        cursor_ts = None
        pages = 0
        while pages < max(1, options["max_pages"]):
            args = {"limit": 100}
            if cursor_id and cursor_ts:
                args.update({"lastItemId": cursor_id, "lastItemTimestamp": cursor_ts})
            data = _mcp("chats_list", args)
            items = (data.get("items") or []) if isinstance(data, dict) else (data or [])
            if not items:
                break
            pages += 1
            for item in items:
                chat_id = str(item.get("id") or "")
                name_key = str(item.get("clientName") or "").strip().lower().lstrip("@")
                candidate_usernames = alias_to_usernames.get(name_key) or set()
                if not chat_id or not candidate_usernames or chat_id in inspected_details:
                    continue
                inspected_details.add(chat_id)
                try:
                    details = _mcp("chats_get", {"chatId": chat_id})
                except Exception:
                    continue
                actual = _username((details or {}).get("username") if isinstance(details, dict) else "")
                if actual and actual in candidate_usernames:
                    matches[actual].add(chat_id)
            if not isinstance(data, dict) or not data.get("hasNextItems"):
                break
            next_id = str(data.get("lastItemId") or "")
            next_ts = data.get("lastItemTimestamp")
            if not next_id or next_ts is None or (next_id, next_ts) == (cursor_id, cursor_ts):
                break
            cursor_id, cursor_ts = next_id, next_ts

        mapped = ambiguous = unresolved = changed = 0
        for username, convs in by_username.items():
            ids = matches.get(username) or set()
            if len(ids) != 1:
                if len(ids) > 1:
                    ambiguous += len(convs)
                else:
                    unresolved += len(convs)
                continue
            chat_id = next(iter(ids))
            mapped += len(convs)
            for conv in convs:
                current = (conv.config or {}).get("outbound_chatplace") or {}
                if str(current.get("chat_id") or "") == chat_id:
                    continue
                changed += 1
                if options["apply"]:
                    conv.config = {**(conv.config or {}), "outbound_chatplace": {
                        "chat_id": chat_id,
                        "username": username,
                        "matched_at": timezone.now().isoformat(),
                        "match": "exact_instagram_username",
                    }}
                    conv.save(update_fields=["config"])

        mode = "APPLY" if options["apply"] else "DRY_RUN"
        self.stdout.write(
            f"{mode}: checked={len(conversations)} usernames={len(by_username)} "
            f"mapped={mapped} changed={changed} unresolved={unresolved} "
            f"ambiguous={ambiguous} without_username={without_username} "
            f"pages={pages} details={len(inspected_details)}"
        )
