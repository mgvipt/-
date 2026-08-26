from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Дотягивает имена контактам-заглушкам ('instagram') по IGSID из прямого Meta-канала"

    def handle(self, *args, **options):
        from apps.crm.models import Contact
        from apps.inbox.models import Conversation
        from apps.inbox.meta import _enrich_contact
        fixed = failed = 0
        for c in Contact.objects.filter(first_name__iexact="instagram"):
            conv = (Conversation.objects.filter(contact=c, channel__kind="instagram", channel__config__meta=True)
                    .exclude(external_chat_id="").exclude(external_chat_id__startswith="comment:").first())
            if not conv:
                continue
            try:
                if _enrich_contact(c, "instagram", conv.external_chat_id):
                    fixed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        self.stdout.write("enriched=%d still_placeholder=%d" % (fixed, failed))
