"""Безпечне дозаповнення імен/username у вже існуючих Meta Instagram-чатах.

За замовчуванням команда працює як DRY_RUN. Запис дозволяється лише з --apply.
"""
from django.core.management.base import BaseCommand

from apps.crm.models import Contact
from apps.inbox.meta import (
    _clean_username,
    _contact_identity_changes,
    _get_or_make_contact,
    _resolve_meta_identity,
)
from apps.inbox.models import Conversation


class Command(BaseCommand):
    help = "DRY_RUN/оновлення імен та username старих Meta Instagram-чатів"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записати зміни (без прапорця лише DRY_RUN)")
        parser.add_argument("--limit", type=int, default=0, help="Максимум чатів для перевірки")
        parser.add_argument("--conversation-id", action="append", type=int, dest="conversation_ids",
                            help="Обробити лише точний chat ID; можна вказати кілька разів")

    @staticmethod
    def _hints(conv):
        tail = str(conv.external_chat_id or "").rsplit(":", 1)[-1].strip()
        profile_id = tail if tail.isdigit() else ""
        username = _clean_username(tail)
        first_in = (conv.messages.filter(direction="in").exclude(sender_name="")
                    .order_by("id").first())
        if first_in:
            username = _clean_username(first_in.sender_name) or username
        return profile_id, username

    @staticmethod
    def _unique_contact(username):
        if not username:
            return None, False
        matches = list(Contact.objects.filter(nickname__iexact=username).order_by("id")[:2])
        return (matches[0], False) if len(matches) == 1 else (None, len(matches) > 1)

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        qs = (Conversation.objects.filter(channel__name="Meta · instagram")
              .select_related("contact").order_by("id"))
        if options.get("conversation_ids"):
            qs = qs.filter(id__in=options["conversation_ids"])
        if options["limit"] > 0:
            qs = qs[:options["limit"]]

        checked = resolvable = contacts_to_create = contacts_to_attach = contacts_to_update = unresolved = ambiguous = 0
        profile_cache = {}
        for conv in qs:
            checked += 1
            profile_id, username_hint = self._hints(conv)
            cache_key = (profile_id, username_hint)
            if cache_key not in profile_cache:
                profile_cache[cache_key] = _resolve_meta_identity(
                    profile_id, "instagram", username=username_hint,
                )
            name, username = profile_cache[cache_key]
            if not name and not username:
                unresolved += 1
                continue
            resolvable += 1
            contact = conv.contact
            if contact is None:
                contact, is_ambiguous = self._unique_contact(username)
                if is_ambiguous:
                    # Два контакти з тим самим ніком не можна зливати автоматично.
                    ambiguous += 1
                    continue
                if contact:
                    contacts_to_attach += 1
                    if apply:
                        conv.contact = contact
                        conv.save(update_fields=["contact"])
                else:
                    contacts_to_create += 1
                    if apply:
                        contact = _get_or_make_contact("instagram", profile_id, name, username)
                        conv.contact = contact
                        conv.save(update_fields=["contact"])
            if contact is not None:
                changes = _contact_identity_changes(contact, "instagram", name, username)
                if changes:
                    contacts_to_update += 1
                    if apply:
                        for field, value in changes.items():
                            setattr(contact, field, value)
                        contact.save(update_fields=list(changes))

        mode = "APPLY" if apply else "DRY_RUN"
        self.stdout.write(
            f"{mode}: checked={checked} resolvable={resolvable} unresolved={unresolved} "
            f"ambiguous={ambiguous} "
            f"create_contacts={contacts_to_create} attach_existing={contacts_to_attach} "
            f"update_contacts={contacts_to_update}"
        )
