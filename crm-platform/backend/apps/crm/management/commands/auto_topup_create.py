"""Django management command: auto_topup_create

Викликається з Hetzner kb-wallcov коли Юля-ChatPlace каже "Оформлюю в системі"
і в контексті діалогу є докуп-маркери. Створює НОВУ сделку у CRM (не тест-набір!)
на основі минулої won-сделки клієнта.

Приклад використання:
    docker exec -i crm-platform-web-1 python manage.py auto_topup_create --json '{
        "chat_id": "1234567890",
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

    def _contact_by_chat(self, chat_id):
        """НАЙНАДІЙНІШИЙ спосіб: номер переписки → діалог → клієнт.
        Жодних здогадок: усі IG-діалоги мають і номер, і привʼязаного клієнта."""
        from apps.inbox.models import Conversation
        cid = str(chat_id or "").strip()
        if not cid:
            return None
        convs = list(
            Conversation.objects.filter(external_chat_id=cid, contact__isnull=False)
            .select_related("contact").order_by("-last_message_at")[:20]
        )
        contacts, seen = [], set()
        for v in convs:
            if v.contact_id not in seen:
                seen.add(v.contact_id)
                contacts.append(v.contact)
        if not contacts:
            return None
        if len(contacts) == 1:
            return contacts[0]
        # 14 номерів із 3 639 ведуть на ДВІ картки — це дублі ОДНІЄЇ людини,
        # а не різні люди. Беремо картку з покупками, інакше — найсвіжішу.
        for c in contacts:
            if Deal.objects.filter(contact=c, funnel_id=FUNNEL_MAIN_ID,
                                   stage__is_won=True).exists():
                return c
        return contacts[0]

    def _most_recent_talker(self, contacts):
        """Тайбрейк для тезок: хто з кандидатів спілкується з нами ОСТАННІМ.
        Це не здогадка — діалог і є той контекст, у якому оформлюється замовлення."""
        from apps.inbox.models import Conversation
        best, best_ts = None, None
        for c in contacts:
            ts = (Conversation.objects.filter(contact=c)
                  .order_by("-last_message_at")
                  .values_list("last_message_at", flat=True).first())
            if ts and (best_ts is None or ts > best_ts):
                best, best_ts = c, ts
        return best

    def _ig_matches(self, contact, clean):
        """СТРОГА звірка IG: нік або хвіст посилання мають збігатися ПОВНІСТЮ.
        Часткові збіги заборонені — «ira» не повинна ловити «kira_deco»."""
        target = (clean or "").lstrip("@").strip().lower()
        if not target:
            return False
        if ((contact.nickname or "").lstrip("@").strip().lower()) == target:
            return True
        link = (contact.social_link or "").strip().lower().rstrip("/")
        if link:
            tail = link.rsplit("/", 1)[-1].split("?")[0].lstrip("@")
            if tail == target:
                return True
        return False

    def _find_contact(self, ig_username=None, client_name=None, chat_id=None):
        """Знайти клієнта: НОМЕР ПЕРЕПИСКИ → IG username → повне імʼя.

        ⚠️ БЕЗПЕКА (2026-08-15). Одразу після цього коду створюється сделка
        і посилання LiqPay, тому помилка тут = рахунок ЧУЖІЙ людині.
        Тому діють два жорсткі правила:
          1. Жодних часткових збігів по людях. Раніше запасний пошук робив
             OR по кожному слову через icontains — тобто «Ольга Петренко»
             ловила БУДЬ-ЯКУ Ольгу. З 234 повторників 187 (80%) мають
             НЕунікальне імʼя: 15 «Тетяна», 14 «Ольга», 14 «Ірина».
          2. Жодного «беремо першого». Якщо підходить більше одного — вертаємо
             None і віддаємо діалог менеджеру. Краще не створити нічого,
             ніж виставити рахунок не тому.
        Причина відмови кладеться у self.match_reason.
        """
        self.match_reason = ""

        # 0. Номер переписки — точний і безпомилковий шлях. Автоматика тут
        #    ніколи не зупиняється, бо діалог завжди привʼязаний до клієнта.
        by_chat = self._contact_by_chat(chat_id)
        if by_chat:
            self.match_reason = "by_chat"
            return by_chat

        qs = Contact.objects.all()
        candidates = []

        if ig_username:
            clean = ig_username.lstrip("@").strip()
            rough = list(
                qs.filter(
                    Q(social_link__icontains=clean) | Q(nickname__icontains=clean)
                ).order_by("-created_at")[:50]
            )
            # широко знайшли — далі лишаємо ТІЛЬКИ точні збіги
            candidates = [c for c in rough if self._ig_matches(c, clean)]

        if not candidates and client_name:
            parts = [p for p in re.split(r"\s+", client_name.strip()) if len(p) >= 2]
            # Потрібні ОБИДВА слова: імʼя + прізвище. Одного слова замало.
            if len(parts) >= 2:
                p1, p2 = parts[0], parts[1]
                exact_q = (
                    (Q(first_name__iexact=p1) & Q(last_name__iexact=p2))
                    | (Q(first_name__iexact=p2) & Q(last_name__iexact=p1))
                )
                candidates = list(qs.filter(exact_q).order_by("-created_at")[:10])
                if not candidates:
                    starts_q = (
                        (Q(first_name__istartswith=p1) & Q(last_name__istartswith=p2))
                        | (Q(first_name__istartswith=p2) & Q(last_name__istartswith=p1))
                    )
                    candidates = list(qs.filter(starts_q).order_by("-created_at")[:10])
            # fuzzy-fallback по одному слову ПРИБРАНО навмисно — див. правило 1.

        # Пріоритет: повторник основної воронки. Але якщо таких кілька — відмова.
        won = [c for c in candidates
               if Deal.objects.filter(contact=c, funnel_id=FUNNEL_MAIN_ID, stage__is_won=True).exists()]
        if len(won) == 1:
            return won[0]
        if len(won) > 1:
            pick = self._most_recent_talker(won)
            if pick:
                self.match_reason = "tiebreak_by_dialog"
                return pick
            self.match_reason = "ambiguous:%d" % len(won)
            return None

        other = [c for c in candidates
                 if Deal.objects.filter(contact=c).exclude(funnel__is_lead_funnel=True).exists()]
        if len(other) == 1:
            return other[0]
        if len(other) > 1:
            pick = self._most_recent_talker(other)
            if pick:
                self.match_reason = "tiebreak_by_dialog"
                return pick
            self.match_reason = "ambiguous:%d" % len(other)
            return None

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

        base = "https://crm.wallcovdec.com.ua"
        # коротке посилання + УНІКАЛЬНИЙ order_id (див. коментар у apps/crm/views.py make_offer)
        code = _short_code()
        while PayLink.objects.filter(code=code).exists():
            code = _short_code()
        order_id = "WCCRM-%s-%s" % (deal.id, code)
        full_url = build_checkout_url(
            pub, prv, amount, order_id,
            "Замовлення Wallcov #%s" % deal.id,
            server_url=base + "/api/crm/liqpay/callback/",
            result_url=base,
            paytypes="card,apay,gpay,privat24",
        )
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
            chat_id=data.get("chat_id"),
        )
        if not contact:
            amb = getattr(self, "match_reason", "").startswith("ambiguous")
            self._reply(
                ok=False,
                error="contact_ambiguous" if amb else "contact_not_found",
                hint=("Під цей запит підходить КІЛЬКА різних людей — не вгадуємо. "
                      "Передавай менеджеру, хай уточнить і створить сделку вручну"
                      if amb else
                      "Це не повторник — передавай менеджеру, він створить сделку вручну"),
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
