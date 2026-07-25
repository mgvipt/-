"""Django management command: auto_topup_create

Викликається з Hetzner kb-wallcov коли Юля-ChatPlace каже "Оформлюю в системі"
і в контексті діалогу є докуп-маркери. Створює НОВУ сделку у CRM (не тест-набір!)
на основі минулої won-сделки клієнта.

Приклад використання:
    docker exec -i crm-platform-web-1 python manage.py auto_topup_create --json '{
        "ig_username": "wallov.hr",
        "client_name": "Степура Ольга",
        "material_query": "мокрий шовк",
        "quantity_kg": 0.3,
        "max_amount": 5000
    }' --dry-run

Повертає JSON у stdout:
    {"ok": true, "dry": true, "would_create": {...}}
або
    {"ok": true, "deal_id": 65890, "amount": "324.00", "pay_link_short": "https://..."}
або
    {"ok": false, "error": "contact_not_found", "hint": "..."}
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.crm.models import Contact, Deal, DealItem, Funnel, PayLink, Stage
from apps.warehouse.models import Product

DEFAULT_MAX_AMOUNT = 3000  # 2026-07-22: змінено з 5000 → 3000 за проханням Олега  # грн — вище передається менеджеру
FUNNEL_MAIN_ID = 15  # "21 Основний продукт"
STAGE_ROZRAHUNOK_KP = "Розрахунок здійснено (КП)"


def _short_code():
    import random
    import string
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(7))


class Command(BaseCommand):
    help = "Створити 'докуп' сделку для клієнта-повторника (виклик з ChatPlace Юлi)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            help="JSON input (якщо не задано — читає з stdin)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Не створювати сделку, тільки показати що буде зроблено",
        )

    def _reply(self, **kw):
        """Print JSON to stdout and exit."""
        self.stdout.write(json.dumps(kw, ensure_ascii=False, default=str))
        sys.exit(0)

    def _find_contact(self, ig_username=None, client_name=None):
        """Знайти клієнта за IG username АБО за іменем.
        Порядок:
          1. Contact.social_link містить ig_username
          2. Contact.nickname == ig_username
          3. Contact.first_name + last_name містить client_name (fuzzy)
        Повертає першого знайденого повторника (має ≥1 сделку не з ліда).
        """
        qs = Contact.objects.all()
        candidates = []

        if ig_username:
            clean = ig_username.lstrip("@").strip()
            candidates = list(
                qs.filter(
                    Q(social_link__icontains=clean)
                    | Q(nickname__iexact=clean)
                    | Q(nickname__icontains=clean)
                ).order_by("-created_at")[:10]
            )

        if not candidates and client_name:
            name = client_name.strip()
            parts = [p for p in re.split(r"\s+", name) if len(p) >= 2]
            # Пошук зі spec-порядком: exact both names > startswith both > icontains
            if len(parts) >= 2:
                # Спочатку — точний матч обох імен (у будь-якому порядку)
                p1, p2 = parts[0], parts[1]
                exact_q = (
                    (Q(first_name__iexact=p1) & Q(last_name__iexact=p2))
                    | (Q(first_name__iexact=p2) & Q(last_name__iexact=p1))
                )
                candidates = list(qs.filter(exact_q).order_by("-created_at")[:10])
                # Якщо exact не знайшов — startswith обох
                if not candidates:
                    starts_q = (
                        (Q(first_name__istartswith=p1) & Q(last_name__istartswith=p2))
                        | (Q(first_name__istartswith=p2) & Q(last_name__istartswith=p1))
                    )
                    candidates = list(qs.filter(starts_q).order_by("-created_at")[:10])
            # Fallback — fuzzy icontains
            if not candidates:
                q = Q()
                for p in parts:
                    q |= Q(first_name__icontains=p) | Q(last_name__icontains=p) | Q(nickname__icontains=p)
                if q:
                    candidates = list(qs.filter(q).order_by("-created_at")[:10])

        # Фільтруємо — тільки повторники (мають хоч 1 won-сделку в основній воронці)
        for c in candidates:
            if Deal.objects.filter(
                contact=c, funnel_id=FUNNEL_MAIN_ID, stage__is_won=True
            ).exists():
                return c

        # Якщо won-сделок нема, повертаємо перший з ≥1 будь-якою сделкою (окрім лідів)
        for c in candidates:
            if Deal.objects.filter(contact=c).exclude(funnel__is_lead_funnel=True).exists():
                return c

        return None

    def _find_product(self, query, prev_deal):
        """Знайти product за fuzzy match. Пріоритет:
          1. Товар з prev_deal.items (клієнт брав раніше — беремо той самий SKU)
          2. Fuzzy match по назві (icontains з кожним словом query)
        Повертає None якщо неоднозначно (>3 матчів) або нема.
        """
        if not query:
            return None

        # 1. З prev_deal — шукаємо продукт що містить слово з query
        query_words = [w.lower() for w in re.split(r"\s+", query) if len(w) >= 3]
        # Стемінг: обрізати закінчення для укр слів (мокрий→мокр, шовк→шовк, дощечка→дощеч)
        query_stems = [(w[:-2] if len(w) >= 5 else w) for w in query_words]
        if prev_deal:
            for item in prev_deal.items.select_related("product").all():
                if not item.product_id or not item.product.is_active:
                    continue
                pname = item.product.name.lower()
                if all(s in pname for s in query_stems):
                    return item.product

        # 2. Пошук у warehouse_product
        # ВАЖЛИВО: тільки реальні товари з ціною > 0, виключаємо тест-набори і викраски (не для докупу)
        from decimal import Decimal as _D
        qs = Product.objects.filter(is_active=True, price__gt=_D("0"))
        for s in query_stems:
            qs = qs.filter(name__icontains=s)
        qs = qs.exclude(name__icontains="тестов").exclude(name__icontains="викраск").exclude(name__icontains="пробник")
        matches = list(qs[:10])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Fallback: якщо серед матчів є product з prev_deal.items — беремо його
            if prev_deal:
                prev_product_ids = {
                    i.product_id for i in prev_deal.items.all() if i.product_id
                }
                for m in matches:
                    if m.id in prev_product_ids:
                        return m
            # інакше — неоднозначно, повертаємо None (передати менеджеру)
            return None
        return None

    def _generate_pay_link(self, deal, amount):
        """Генеруємо LiqPay short link — те саме що робить кнопка «Прийняти оплату → LiqPay» у CRM."""
        from apps.crm.liqpay import build_checkout_url

        pub = getattr(settings, "LIQPAY_PUBLIC_KEY", "")
        prv = getattr(settings, "LIQPAY_PRIVATE_KEY", "")
        if not (pub and prv):
            return None

        order_id = "WCCRM-%s-%s" % (deal.id, str(deal.id * 7919 + int(amount))[-6:])
        base = "https://crm.wallcovdec.com.ua"
        full_url = build_checkout_url(
            pub, prv, amount, order_id,
            "Замовлення Wallcov #%s" % deal.id,
            server_url=base + "/api/crm/liqpay/callback/",
            result_url=base,
            paytypes="card,apay,gpay,privat24",
        )
        # коротке посилання
        code = _short_code()
        while PayLink.objects.filter(code=code).exists():
            code = _short_code()
        PayLink.objects.create(code=code, deal=deal, target=full_url)
        return "%s/p/%s/" % (base, code)

    def handle(self, *args, **opts):
        # 1. Parse input
        raw = opts.get("json") or sys.stdin.read()
        try:
            data = json.loads(raw)
        except Exception as e:
            self._reply(ok=False, error="bad_json", detail=str(e))

        dry = bool(opts.get("dry_run"))

        # 2. Find contact
        contact = self._find_contact(
            ig_username=data.get("ig_username"),
            client_name=data.get("client_name"),
        )
        if not contact:
            self._reply(
                ok=False, error="contact_not_found",
                hint="Це не повторник — передавай менеджеру, він створить сделку вручну",
                query={"ig": data.get("ig_username"), "name": data.get("client_name")},
            )

        # 3. Find last won deal (для np_data + product lookup)
        prev_deal = (
            Deal.objects.filter(contact=contact, funnel_id=FUNNEL_MAIN_ID, stage__is_won=True)
            .order_by("-created_at").first()
        )
        if not prev_deal:
            # може бути won в іншій воронці, або просто без won — беремо останню будь-яку
            prev_deal = (
                Deal.objects.filter(contact=contact)
                .exclude(funnel__is_lead_funnel=True)
                .order_by("-created_at").first()
            )
        if not prev_deal:
            self._reply(
                ok=False, error="no_prev_deal",
                contact_id=contact.id,
                hint="У контакта нема жодної сделки — не можу автоматично взяти адресу/матеріал",
            )

        # 4. Find product
        product = self._find_product(
            query=data.get("material_query"),
            prev_deal=prev_deal,
        )
        if not product:
            self._reply(
                ok=False, error="product_not_found",
                contact_id=contact.id,
                prev_deal_id=prev_deal.id,
                material_query=data.get("material_query"),
                hint="Не знайшов чіткий матч у номенклатурі — передай менеджеру",
            )

        # 5. Compute amount + safety cap
        try:
            qty = Decimal(str(data.get("quantity_kg") or 0))
        except Exception:
            qty = Decimal("0")
        if qty <= 0:
            self._reply(ok=False, error="bad_quantity", quantity=str(qty))

        price = product.price or Decimal("0")
        amount = price * qty
        max_amount = Decimal(str(data.get("max_amount") or DEFAULT_MAX_AMOUNT))
        if amount > max_amount:
            self._reply(
                ok=False, error="amount_too_high",
                amount=str(amount), max=str(max_amount),
                hint="Сума докупу перевищує ліміт — передавай менеджеру",
            )

        # 6. DRY RUN — просто повертаємо що б зробив
        if dry:
            self._reply(
                ok=True, dry=True,
                would_create={
                    "contact_id": contact.id,
                    "contact_name": str(contact),
                    "prev_deal_id": prev_deal.id,
                    "prev_deal_title": prev_deal.title,
                    "product_id": product.id,
                    "product_name": product.name,
                    "quantity_kg": str(qty),
                    "unit_price": str(price),
                    "amount": str(amount),
                    "copy_np_data_from": prev_deal.id,
                    "np_data_recipient": (prev_deal.np_data or {}).get("recipient", {}).get("name"),
                },
            )

        # 7. LIVE — Create deal
        stage = (
            Stage.objects.filter(funnel_id=FUNNEL_MAIN_ID, name__iexact=STAGE_ROZRAHUNOK_KP).first()
            or Stage.objects.filter(funnel_id=FUNNEL_MAIN_ID).order_by("order").first()
        )
        # Marker для координації з run_agent_sweep — інші AI не чіпають цю сделку
        # до моменту оплати (потім LiqPay callback замінить value на "paid")
        from django.utils import timezone as _tz
        _marker = [
            {"label": "AI-AutoTopup", "value": "waiting_for_payment",
             "created_at": _tz.now().isoformat()},
            {"label": "AI-Source", "value": "auto_topup_flow"},
        ]
        # np_data копіюємо з prev — АЛЕ прибираємо специфічні для попередньої відправки поля
        # (щоб інші агенти не думали що це та сама доставка)
        _np_clean = dict(prev_deal.np_data or {})
        for _f in ("ttn_ref", "delivery_acts", "msg_arrived", "msg_shipped", "cargo_details"):
            _np_clean.pop(_f, None)

        deal = Deal.objects.create(
            title=f"{contact} — докуп {qty}кг {product.name[:60]}",
            contact=contact,
            funnel_id=FUNNEL_MAIN_ID,
            stage=stage,
            amount=amount,
            source="instagram",
            pay_type="Повна оплата",
            np_data=_np_clean,
            card_fields=_marker,
        )
        DealItem.objects.create(
            deal=deal,
            product=product,
            quantity=qty,
            price=price,
            cost=(product.cost or Decimal("0")) * qty,
        )

        # 8. Generate LiqPay short link
        pay_link = self._generate_pay_link(deal, amount)

        self._reply(
            ok=True,
            deal_id=deal.id,
            deal_title=deal.title,
            contact_id=contact.id,
            product_id=product.id,
            quantity_kg=str(qty),
            amount=str(amount),
            pay_link_short=pay_link,
            note="Сделка створена у воронці 'Основний продукт', стадія 'Розрахунок здійснено (КП)'. np_data скопійовано з попередньої сделки #%d" % prev_deal.id,
        )
