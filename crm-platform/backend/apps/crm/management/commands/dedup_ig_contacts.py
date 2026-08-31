# -*- coding: utf-8 -*-
import re
from django.core.management.base import BaseCommand
from django.db.models import Count
from apps.crm.models import Contact, Deal, Lead
from apps.inbox.models import Conversation


def _handle(c):
    """ТІЛЬКИ реальний IG-нік з посилання (ASCII). БЕЗ fallback на нік/імʼя —
    інакше різні люди з однаковим імʼям (людмила/оксана) склеяться. IG-нік унікальний."""
    sl = (c.social_link or "").strip().lower()
    m = re.search(r"instagram\.com/([a-z0-9._]{2,})", sl)
    return m.group(1) if m else None


class Command(BaseCommand):
    help = "Обʼєднати дублі IG-контактів за ТОЧНИМ ніком (діалоги+ліди → до контакта з історією). DRY за замовч."

    def add_arguments(self, p):
        p.add_argument("--live", action="store_true", help="реально виконати (без цього — DRY)")
        p.add_argument("--handle", default="", help="обробити ТІЛЬКИ цей нік (для тесту)")

    def handle(self, *a, **o):
        live = o["live"]
        only = (o.get("handle") or "").strip().lower()
        groups = {}
        for c in Contact.objects.all().only("id", "social_link", "nickname"):
            h = _handle(c)
            if h:
                groups.setdefault(h, []).append(c.id)
        merged = skipped = 0
        for h, ids in groups.items():
            if len(ids) < 2:
                continue
            if only and h != only:
                continue
            cs = list(Contact.objects.filter(id__in=ids))
            # keeper = має сделки → інакше найстаріший
            with_deals = [c for c in cs if Deal.objects.filter(contact=c).exists()]
            if len(with_deals) > 1:
                skipped += 1
                self.stdout.write("SKIP @%s: у %d контактів є сделки — ручний розбір: %s" % (h, len(with_deals), [c.id for c in with_deals]))
                continue
            keeper = with_deals[0] if with_deals else min(cs, key=lambda c: c.id)
            for c in cs:
                if c.id == keeper.id:
                    continue
                if Deal.objects.filter(contact=c).exists():
                    skipped += 1
                    self.stdout.write("SKIP @%s dup #%d має сделки — не чіпаю" % (h, c.id))
                    continue
                nconv = Conversation.objects.filter(contact=c).count()
                nlead = Lead.objects.filter(contact=c).count()
                self.stdout.write("%s @%s: dup #%d → keeper #%d (convs=%d leads=%d)" % ("MERGE" if live else "DRY", h, c.id, keeper.id, nconv, nlead))
                if live:
                    Conversation.objects.filter(contact=c).update(contact=keeper)
                    Lead.objects.filter(contact=c).update(contact=keeper)
                    # посилання дубля переносимо КЕЙПЕРУ (щоб не загубити другий акаунт
                    # клієнта), а в самому хвості чистимо ВСІ поля з акаунтами.
                    # 31.08.2026: раніше чистили лише social_link+nickname, а messengers
                    # лишався — і хвіст знову спливав у пошуку дублів як «новий дубль».
                    keep_links = list(keeper.messengers or [])
                    for link in ([c.social_link] + list(c.messengers or [])):
                        link = (link or "").strip()
                        if link and link not in keep_links:
                            keep_links.append(link)
                    if keep_links != list(keeper.messengers or []):
                        keeper.messengers = keep_links
                        keeper.save(update_fields=["messengers"])
                    c.comment = ("[обʼєднано → #%d] " % keeper.id) + (c.comment or "")
                    c.social_link = ""; c.nickname = ""; c.messengers = []; c.links_extra = []
                    c.save(update_fields=["comment", "social_link", "nickname", "messengers", "links_extra"])
                merged += 1
        self.stdout.write("=== %s: merged=%d skipped=%d ===" % ("LIVE" if live else "DRY", merged, skipped))
