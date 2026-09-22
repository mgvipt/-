# -*- coding: utf-8 -*-
"""22.09.2026 (Олег: «продавець CRM має стартувати з матеріалу реклами, з якої прийшов клієнт»).
Реклама клієнта — з атрибуції його ліда/сделки (meta_attribution, source_kind=paid_ad).
Одне джерело для плашки «Прийшов з реклами», продавця CRM і ШІ-РОП."""
import re

_DATE = re.compile(r"^\d{1,2}\.\d{1,2}(\.\d{2,4})?$")
_PREFIX = re.compile(r"^(lal|ret|lookalike|la|retarget\w*)\s+", re.I)
_GENERAL = ("загальн", "общ", "general", "бренд")


def ad_info(conv):
    """{"ad_title", "ad_thumb", "content_id", "ad_id", "campaign_name"} або {} — лише читання."""
    if not conv or not conv.contact_id:
        return {}
    from itertools import chain
    from apps.crm.models import Deal, Lead
    # 14.09.2026 (meta-attr): сконвертований лід видаляється, мітка живе на угоді → читаємо і угоди
    for obj in chain(
            Lead.objects.filter(contact_id=conv.contact_id)
            .exclude(meta_attribution={}).exclude(meta_attribution__isnull=True).order_by("-id")[:8],
            Deal.objects.filter(contact_id=conv.contact_id)
            .exclude(meta_attribution={}).exclude(meta_attribution__isnull=True).order_by("-id")[:8]):
        a = obj.meta_attribution or {}
        if a.get("source_kind") == "paid_ad" and (a.get("ad_title") or a.get("ad_thumb")):
            return {
                "ad_title": a.get("ad_title") or "",
                "ad_thumb": a.get("ad_thumb") or "",
                "content_id": a.get("content_id") or "",
                "ad_id": a.get("ad_id") or "",
                "campaign_name": a.get("campaign_name") or "",
            }
    return {}


def ad_topic(title):
    """«29.04.26 | Галатея | 02.09.26» → «Галатея»; «lal … | Галатея | …» → «Галатея»;
    загальна реклама («Загальний») або без назви → ""."""
    parts = []
    for p in (title or "").split("|"):
        p = _PREFIX.sub("", p.strip()).strip()
        words = [w for w in p.split() if not _DATE.match(w)]
        p = " ".join(words).strip()
        if p and not _DATE.match(p):
            parts.append(p)
    topic = " ".join(parts).strip()
    if not topic or any(g in topic.lower() for g in _GENERAL):
        return ""
    return topic[:80]


def ad_prompt(conv):
    """Рядок для промпту ШІ або "" (клієнт не з реклами / реклама загальна)."""
    try:
        topic = ad_topic(ad_info(conv).get("ad_title"))
    except Exception:
        return ""
    if not topic:
        return ""
    return ("КЛІЄНТ ПРИЙШОВ З РЕКЛАМИ: «%s». Якщо клієнт сам не назвав інший матеріал — мова саме про %s: "
            "НЕ перепитуй, який матеріал його цікавить; каталог кольорів, ціни й тест-набір — саме цього "
            "матеріалу. Якщо клієнт питає про інше — відповідай про те, що він питає." % (topic, topic))
