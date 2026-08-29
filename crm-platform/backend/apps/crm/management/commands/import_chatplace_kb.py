import json
from django.core.management.base import BaseCommand
from apps.crm.models import KbEntry, KbUnknownQuestion


class Command(BaseCommand):
    help = "Імпорт бази знань і невідомих питань з ChatPlace (JSON-файли)"

    def add_arguments(self, p):
        p.add_argument("--kb", default="/tmp/cp_kb.json")
        p.add_argument("--questions", default="/tmp/cp_questions.json")

    def handle(self, *a, **o):
        kb = json.load(open(o["kb"], encoding="utf-8"))
        created = updated = 0
        for it in kb:
            ext = str(it.get("id") or "")
            obj, is_new = KbEntry.objects.update_or_create(
                ext_id=ext,
                defaults={
                    "question": (it.get("question") or "").strip(),
                    "answer": (it.get("answer") or "").strip(),
                    "specific_rules": (it.get("specificRules") or "") if it.get("specificRules") not in (None, "None") else "",
                    "source": "chatplace",
                    "client_chat_count": int(it.get("clientChatCount") or 0),
                },
            )
            created += int(is_new); updated += int(not is_new)
        self.stdout.write("KB: created=%d updated=%d total=%d" % (created, updated, KbEntry.objects.count()))

        qs = json.load(open(o["questions"], encoding="utf-8"))
        qc = qu = 0
        for it in qs:
            ext = str(it.get("id") or "")
            _, is_new = KbUnknownQuestion.objects.update_or_create(
                ext_id=ext,
                defaults={"question": (it.get("question") or "").strip(), "source": "chatplace"},
            )
            qc += int(is_new); qu += int(not is_new)
        self.stdout.write("Questions: created=%d updated=%d total=%d" % (qc, qu, KbUnknownQuestion.objects.count()))
