"""Підмітання рекламної атрибуції: переносить мітку paid_ad з рекламного ліда
на СДЕЛКИ того самого клієнта, звʼязані за ТОЧНИМ IG-username (nickname).

БЕЗПЕЧНО: тільки ДОДАЄ мітку туди, де її ще нема (source_kind != paid_ad).
Нічого не перезаписує, не видаляє, не чіпає живий Meta-вебхук. Ідемпотентно.
Без --apply — лише DRY-RUN (друкує, що зробив би).

Навіщо: рекламний клік створює контакт Meta з міткою, а покупку людина робить
через ChatPlace (інший контакт того самого username). Ця команда доводить мітку
до сделки, щоб ланцюг реклама→продаж→оплата→Meta ROAS замкнувся.
"""
from django.core.management.base import BaseCommand
from apps.crm.models import Lead, Deal, Contact


class Command(BaseCommand):
    help = "Перенести мітку paid_ad на сделки того самого клієнта по IG-username"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="реально записати (без прапорця — DRY-RUN)")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        # найкраща мітка на кожен username (з ad_id пріоритетніша)
        best = {}
        for l in Lead.objects.filter(meta_attribution__source_kind="paid_ad").select_related("contact"):
            c = l.contact
            if not c:
                continue
            u = (c.nickname or "").strip().lstrip("@").lower()
            if not u:
                continue
            attr = l.meta_attribution or {}
            cur = best.get(u)
            if cur is None or (attr.get("ad_id") and not (cur.get("ad_id"))):
                best[u] = attr
        tagged_deals = 0
        tagged_leads = 0
        touched_usernames = 0
        for u, attr in best.items():
            contacts = list(Contact.objects.filter(nickname__iexact=u).values_list("id", flat=True))
            if not contacts:
                continue
            # сделки цих контактів без мітки paid_ad
            deals = Deal.objects.filter(contact_id__in=contacts)
            hit = False
            for d in deals:
                if (d.meta_attribution or {}).get("source_kind") != "paid_ad":
                    hit = True
                    tagged_deals += 1
                    if apply:
                        d.meta_attribution = attr
                        d.save(update_fields=["meta_attribution"])
            # ліди тих самих контактів без мітки (щоб узгодити двійників)
            for l2 in Lead.objects.filter(contact_id__in=contacts):
                if (l2.meta_attribution or {}).get("source_kind") != "paid_ad":
                    hit = True
                    tagged_leads += 1
                    if apply:
                        l2.meta_attribution = attr
                        l2.save(update_fields=["meta_attribution"])
            if hit:
                touched_usernames += 1
        # ── ДОЗАПОВНЕННЯ КАМПАНІЇ: Meta у вебхуку віддає лише ad_id (номер оголошення),
        #    а campaign_id — ні. Але звʼязок «оголошення → кампанія» вже є у нас у
        #    MetaAdDailyStat (синк реклами). Тягнемо звідти, щоб звіт можна було
        #    згорнути по кампаніях, а не лише по оголошеннях. Тільки де кампанії ще нема.
        from apps.crm.models import MetaAdDailyStat
        camp_map = {}
        for row in MetaAdDailyStat.objects.exclude(campaign_id="").exclude(campaign_id=None)\
                                          .values("object_id", "ad_id", "campaign_id", "campaign_name", "adset_id"):
            for key in (row.get("object_id"), row.get("ad_id")):
                if key and key not in camp_map:
                    camp_map[str(key)] = row
        camp_filled = 0
        for model in (Lead, Deal):
            for obj in model.objects.filter(meta_attribution__source_kind="paid_ad"):
                attr = obj.meta_attribution or {}
                if attr.get("campaign_id"):
                    continue
                row = camp_map.get(str(attr.get("ad_id") or ""))
                if not row:
                    continue
                attr["campaign_id"] = str(row.get("campaign_id") or "")[:180]
                attr["campaign_name"] = str(row.get("campaign_name") or "")[:180]
                if row.get("adset_id") and not attr.get("adset_id"):
                    attr["adset_id"] = str(row.get("adset_id"))[:180]
                camp_filled += 1
                if apply:
                    obj.meta_attribution = attr
                    obj.save(update_fields=["meta_attribution"])

        mode = "APPLIED" if apply else "DRY-RUN"
        self.stdout.write(f"[{mode}] usernames з рекламою: {len(best)} | зачеплено username: {touched_usernames} "
                          f"| сделок отримали мітку: {tagged_deals} | лідів-двійників узгоджено: {tagged_leads} "
                          f"| проставлено кампаній: {camp_filled}")
