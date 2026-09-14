"""Продажі по креативах Meta (14.09.2026, meta-creatives).

Вкладка «Маркетинг → Meta → Креативи»: для кожного оголошення — скільки звернень, угод,
оплачених угод і грошей дала саме ця реклама за обраний період.

Правила (без змішування):
  • ТОЧНО з оголошення — лише мітка Meta з ad_id (source_kind paid_ad / lead_form,
    platform instagram|facebook) — те саме, що has_verified_meta_attribution + ad_id;
  • «ймовірно з реклами» (перше повідомлення = текст кнопки) ad_id НЕ МАЄ — тому йде окремим
    блоком по фразі кнопки і НІКОЛИ не додається до цифр конкретного оголошення;
  • період = дата СТВОРЕННЯ ліда/угоди (як «Угоди · успішні» у таблиці оголошень);
    гроші — усі надходження по цих угодах у журналі (Transaction direction="in", amount_uah),
    навіть якщо оплата прийшла вже після періоду;
  • оплачена угода = стадія «успішна» АБО є хоча б одне надходження в журналі;
  • звернення = різні люди (контакт) з лідом/угодою з цієї реклами за період.

Фіксована кількість запитів (угоди разом із сумою надходжень — одним запитом, ліди, назви і
витрати оголошень) — незалежно від кількості креативів.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasPermCode

from . import services

EXACT_PLATFORMS = ("instagram", "facebook")
LIST_LIMIT = 100          # скільки угод показуємо у випадайці одного креативу
_ATTR_Q = (Q(meta_attribution__has_key="ad_id")
           | Q(meta_attribution__source_kind=services.LIKELY_KIND)
           | Q(meta_attribution__class=services.CLASS_LIKELY))


def exact_ad_id(attr):
    """ad_id точної мітки Meta або "" (ймовірна / органіка / без ID — не рахуємо за оголошенням)."""
    if not isinstance(attr, dict) or not services.is_exact(attr):
        return ""
    if str(attr.get("platform") or "") not in EXACT_PLATFORMS:
        return ""
    return str(attr.get("ad_id") or "").strip()


def parse_period(params):
    today = timezone.localdate()
    date_from = parse_date(params.get("from") or "") or (today - timedelta(days=29))
    date_to = parse_date(params.get("to") or "") or today
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _money(value):
    return round(float(value or 0), 2)


def _new_group():
    return {"people": set(), "deals": [], "paid": 0, "revenue": Decimal("0")}


def creative_sales(date_from, date_to, user):
    from apps.crm.models import Deal, Lead, MetaAdDailyStat

    show_money = bool(user.is_superuser or user.has_perm_code("marketing.money"))
    can_open = bool(user.is_superuser or user.has_perm_code("deal.view"))
    see_all_deals = bool(user.is_superuser or user.can_see_all_deals())

    income = Q(transactions__direction="in")
    money_field = DecimalField(max_digits=16, decimal_places=2)
    # запит 1: угоди періоду з міткою + сума і кількість надходжень з журналу (один JOIN)
    deal_rows = list(
        Deal.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        .filter(_ATTR_Q)
        .annotate(
            income_sum=Sum(Coalesce(NullIf(F("transactions__amount_uah"), Value(Decimal("0"))),
                                    F("transactions__amount"), output_field=money_field),
                           filter=income, output_field=money_field),
            income_n=Count("transactions", filter=income),
        )
        .values("id", "title", "meta_attribution", "contact_id", "owner_id", "created_at",
                "stage__name", "stage__is_won", "funnel__name", "income_sum", "income_n")
        .order_by("-created_at", "-id")
    )
    # запит 2: ліди періоду з міткою (сконвертовані ліди видаляються — тому люди рахуються і з угод)
    lead_rows = list(
        Lead.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        .filter(_ATTR_Q).values("id", "contact_id", "meta_attribution")
    )

    by_ad = defaultdict(_new_group)
    by_phrase = defaultdict(_new_group)
    ad_titles = {}
    exact_without_ad = {"deals": 0, "paid": 0}

    def target_for(attr):
        ad_id = exact_ad_id(attr)
        if ad_id:
            if attr.get("ad_title") and ad_id not in ad_titles:
                ad_titles[ad_id] = str(attr.get("ad_title"))
            return by_ad[ad_id]
        if services.is_likely(attr):
            return by_phrase[str(attr.get("phrase") or "").strip() or "—"]
        return None

    for row in deal_rows:
        attr = row["meta_attribution"] or {}
        revenue = row["income_sum"] or Decimal("0")
        paid = bool(row["stage__is_won"] or row["income_n"])
        group = target_for(attr)
        if group is None:
            if services.is_exact(attr):
                exact_without_ad["deals"] += 1
                exact_without_ad["paid"] += int(paid)
            continue
        group["people"].add(("c", row["contact_id"]) if row["contact_id"] else ("d", row["id"]))
        group["deals"].append({
            "id": row["id"], "title": row["title"] or "", "stage": row["stage__name"] or "",
            "funnel": row["funnel__name"] or "", "won": bool(row["stage__is_won"]), "paid": paid,
            "revenue": revenue, "owner_id": row["owner_id"],
            "created_at": timezone.localtime(row["created_at"]).date().isoformat() if row["created_at"] else "",
        })
        if paid:
            group["paid"] += 1
        group["revenue"] += revenue

    for row in lead_rows:
        group = target_for(row["meta_attribution"] or {})
        if group is not None:
            group["people"].add(("c", row["contact_id"]) if row["contact_id"] else ("l", row["id"]))

    ad_ids = sorted(by_ad)
    ad_meta, ad_spend = {}, {}
    if ad_ids:
        # запит 3: остання назва/картинка кожного оголошення (DISTINCT ON — Postgres)
        for row in (MetaAdDailyStat.objects.filter(level="ad", ad_id__in=ad_ids)
                    .order_by("ad_id", "-date", "-id").distinct("ad_id")
                    .values("ad_id", "ad_name", "campaign_name", "thumbnail_url")):
            ad_meta[row["ad_id"]] = row
        # запит 4: витрати в гривні за той самий період (якщо хоч один день без курсу — «—»)
        for row in (MetaAdDailyStat.objects.filter(level="ad", ad_id__in=ad_ids,
                                                   date__gte=date_from, date__lte=date_to)
                    .values("ad_id").annotate(
                        uah=Sum("spend_uah"),
                        no_fx=Count("id", filter=Q(spend_uah__isnull=True, spend__gt=0)))):
            ad_spend[row["ad_id"]] = None if row["no_fx"] else row["uah"]

    def finish(group, **extra):
        deals = sorted(group["deals"], key=lambda d: (not d["paid"], -float(d["revenue"]), d["id"] * -1))
        visible = deals if see_all_deals else [d for d in deals if d["owner_id"] == user.id]
        out = {
            "leads": len(group["people"]), "deals": len(deals), "paid": group["paid"],
            "revenue": _money(group["revenue"]) if show_money else None,
            "deals_list": [], "deals_hidden": 0,
            **extra,
        }
        if can_open:
            shown = visible[:LIST_LIMIT]
            out["deals_list"] = [{
                "id": d["id"], "title": d["title"], "stage": d["stage"], "funnel": d["funnel"],
                "won": d["won"], "paid": d["paid"], "created_at": d["created_at"],
                "revenue": _money(d["revenue"]) if show_money else None,
            } for d in shown]
            out["deals_hidden"] = len(deals) - len(shown)
        return out

    result_ads = {}
    for ad_id in ad_ids:
        meta = ad_meta.get(ad_id) or {}
        spend = ad_spend.get(ad_id, 0)
        revenue = by_ad[ad_id]["revenue"]
        result_ads[ad_id] = finish(
            by_ad[ad_id], ad_id=ad_id,
            title=meta.get("ad_name") or ad_titles.get(ad_id) or "",
            campaign_name=meta.get("campaign_name") or "",
            thumbnail_url=meta.get("thumbnail_url") or "",
            spend_uah=None if spend is None else _money(spend),
            revenue_per_uah=(round(float(revenue) / float(spend), 2)
                             if (show_money and spend) else None),
        )
    likely = [finish(group, phrase=phrase) for phrase, group in by_phrase.items()]
    likely.sort(key=lambda g: (-(g["revenue"] or 0), -g["paid"], -g["deals"], g["phrase"]))

    def total(groups):
        return {
            "leads": len(set().union(*[g["people"] for g in groups])) if groups else 0,
            "deals": sum(len(g["deals"]) for g in groups),
            "paid": sum(g["paid"] for g in groups),
            "revenue": _money(sum((g["revenue"] for g in groups), Decimal("0"))) if show_money else None,
        }

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "rule": "created_in_period",
        "show_money": show_money,
        "can_open_deals": can_open,
        "deals_limited_to_own": bool(can_open and not see_all_deals),
        "by_ad": result_ads,
        "likely_by_phrase": likely,
        "totals": {
            "exact": total(list(by_ad.values())),
            "likely": total(list(by_phrase.values())),
            "exact_without_ad": exact_without_ad,
        },
    }


class CreativeSalesView(APIView):
    """GET /api/meta-attr/creative-sales/?from=&to= — лише читання. Право як у вкладки: marketing.view;
    гроші — лише з marketing.money; список угод — лише з deal.view (без deal.view.all — тільки свої)."""
    permission_classes = [HasPermCode]
    required_perm = "marketing.view"

    def get(self, request):
        date_from, date_to = parse_period(request.GET)
        return Response(creative_sales(date_from, date_to, request.user))
