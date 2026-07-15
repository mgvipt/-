import re
import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.common.permissions import HasPermCode
from apps.crm.models import Contact, Deal, DealItem, Funnel, log_activity
from apps.warehouse.models import Product as WarehouseProduct
from .models import IntegrationSettings, ShopOrderImport
from . import adapters

PROVIDERS = {
    "liqpay": ["public_key", "private_key", "currency"],
    "checkbox": ["token", "license_key"],
    "novaposhta": ["api_key", "sender_ref", "sender_city_ref", "sender_contact", "sender_phone"],
    "email_invoices": ["imap_host", "email", "app_password", "senders"],
}


def _mask(v: str) -> str:
    if not v or len(v) < 6:
        return "••••" if v else ""
    return v[:3] + "•••" + v[-2:]


from rest_framework.permissions import BasePermission as _BasePerm


class ManagePerm(_BasePerm):
    """Лише адмін (roles.manage / superuser). Інтеграції = чутливі ключі (оплата/фіскалізація/НП), співробітникам не даємо."""
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if getattr(u, "is_superuser", False):
            return True
        return hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage")


class IntegrationSettingsView(APIView):
    """Чтение (с маскировкой ключей) и сохранение настроек интеграций."""
    permission_classes = [ManagePerm]

    def get(self, request):
        out = []
        for prov, fields in PROVIDERS.items():
            obj = IntegrationSettings.objects.filter(provider=prov).first()
            cfg = (obj.config if obj else {}) or {}
            masked = {f: _mask(str(cfg.get(f, ""))) for f in fields}
            out.append({"provider": prov, "fields": fields, "values": masked,
                        "is_active": obj.is_active if obj else False})
        return Response(out)

    def post(self, request):
        prov = request.data.get("provider")
        if prov not in PROVIDERS:
            return Response({"detail": "Неизвестный провайдер"}, status=400)
        obj, _ = IntegrationSettings.objects.get_or_create(provider=prov)
        cfg = obj.config or {}
        # обновляем только переданные непустые поля (чтобы не затирать ключи маской)
        for f in PROVIDERS[prov]:
            val = request.data.get(f)
            if val:
                cfg[f] = val
        obj.config = cfg
        if "is_active" in request.data:
            obj.is_active = bool(request.data["is_active"])
        obj.save()
        return Response({"ok": True})


class LiqpayLinkView(APIView):
    def post(self, request):
        deal = Deal.objects.filter(pk=request.data.get("deal")).first()
        u = request.user
        if deal and not (u.is_superuser or u.can_see_all_deals() or deal.owner_id == u.id):
            return Response({"detail": "Немає доступу до цієї сделки"}, status=status.HTTP_403_FORBIDDEN)
        amount = request.data.get("amount") or (deal.amount if deal else 0)
        try:
            link = adapters.liqpay_checkout_link(
                amount, deal.id if deal else "test", f"Оплата за {deal.title if deal else 'замовлення'}")
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"link": link})


class NovaPoshtaTrackView(APIView):
    def post(self, request):
        try:
            data = adapters.np_track(request.data.get("ttn", ""))
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)


class ShopOrderWebhookView(APIView):
    """Принимает подписанные заказы Laravel-магазина без доступа к клиентским чатам."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        auth_error = self._verify_signature(request)
        if auth_error:
            return auth_error

        try:
            body = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Response({"detail": "Некорректный JSON"}, status=400)

        event_uuid = str(body.get("event_uuid") or "").strip()
        order = body.get("order") or {}
        order_number = str(order.get("number") or "").strip()
        items = order.get("items") or []
        if not event_uuid or not order_number or not order.get("phone") or not items:
            return Response({"detail": "Не хватает данных заказа"}, status=400)
        try:
            uuid.UUID(event_uuid)
        except (ValueError, AttributeError):
            return Response({"detail": "Некорректный идентификатор события"}, status=400)
        if len(items) > 100:
            return Response({"detail": "Слишком много позиций в заказе"}, status=400)

        existing = ShopOrderImport.objects.filter(event_uuid=event_uuid).select_related("deal").first()
        if existing and existing.deal_id:
            return Response({"ok": True, "duplicate": True, "deal_id": existing.deal_id})

        try:
            total = Decimal(str(order.get("total") or "0"))
        except InvalidOperation:
            return Response({"detail": "Некорректная сумма заказа"}, status=400)
        if total < 0:
            return Response({"detail": "Некорректная сумма заказа"}, status=400)

        normalised_items = []
        try:
            for item in items:
                qty = Decimal(str(item.get("quantity") or "1"))
                unit_price = Decimal(str(item.get("unit_price") or "0"))
                if qty <= 0 or unit_price < 0:
                    raise ValueError
                normalised_items.append((item, qty, unit_price))
        except (AttributeError, InvalidOperation, ValueError):
            return Response({"detail": "Некорректная позиция заказа"}, status=400)

        resolved_items = []
        for item, qty, unit_price in normalised_items:
            sku = str(item.get("sku") or "").strip()
            product = WarehouseProduct.objects.filter(sku=sku, is_active=True).first() if sku else None
            if item.get("type") == "sample" and product is None:
                return Response(
                    {"detail": f"Тест-набор {sku or 'без SKU'} отсутствует в номенклатуре CRM"},
                    status=422,
                )
            resolved_items.append((item, qty, unit_price, product))

        funnel_name = "23 Інтернет-магазин"
        funnel = Funnel.objects.filter(name=funnel_name).prefetch_related("stages").first()
        if funnel is None or not funnel.stages.exists():
            return Response({"detail": f"В CRM не настроена воронка {funnel_name}"}, status=503)
        stage = funnel.stages.order_by("order", "id").first()

        with transaction.atomic():
            imported, _ = ShopOrderImport.objects.select_for_update().get_or_create(
                order_number=order_number,
                defaults={"event_uuid": event_uuid, "payload": body},
            )
            if imported.deal_id:
                return Response({"ok": True, "duplicate": True, "deal_id": imported.deal_id})

            phone = self._normalise_phone(str(order.get("phone") or ""))
            contact = Contact.objects.filter(phone=phone).order_by("id").first()
            name_parts = str(order.get("customer_name") or "").strip().split(maxsplit=1)
            if contact is None:
                contact = Contact.objects.create(
                    first_name=name_parts[0] if name_parts else "",
                    last_name=name_parts[1] if len(name_parts) > 1 else "",
                    phone=phone,
                    email=str(order.get("email") or "").strip(),
                    channels=["site"],
                    source="site",
                    address=self._delivery_label(order),
                )
            else:
                changed = []
                channels = list(contact.channels or [])
                if contact.first_name.strip().casefold() in {"", "гость", "гість", "guest"} and name_parts:
                    contact.first_name = name_parts[0]
                    contact.last_name = name_parts[1] if len(name_parts) > 1 else ""
                    changed.extend(["first_name", "last_name"])
                if "site" not in channels:
                    contact.channels = channels + ["site"]
                    changed.append("channels")
                if not contact.email and order.get("email"):
                    contact.email = str(order["email"]).strip()
                    changed.append("email")
                if not contact.address:
                    contact.address = self._delivery_label(order)
                    changed.append("address")
                if changed:
                    contact.save(update_fields=changed)

            deal = Deal.objects.create(
                title=f"Сайт {order_number} — {order.get('customer_name') or phone}",
                contact=contact,
                funnel=funnel,
                stage=stage,
                source="site",
                amount=total,
                pay_type=self._payment_label(str(order.get("payment_method") or "")),
                is_seen=False,
                np_data={
                    "source": "wallcov-shop",
                    "city": order.get("city"),
                    "city_ref": order.get("city_ref"),
                    "delivery_type": order.get("delivery_type"),
                    "branch": order.get("delivery_branch"),
                    "branch_ref": order.get("delivery_branch_ref"),
                },
                qualification={"shop_order": order_number, "attribution": order.get("attribution") or {}},
                card_fields=self._card_fields(order),
            )
            for item, qty, unit_price, product in resolved_items:
                if product is not None:
                    DealItem.objects.create(
                        deal=deal,
                        product=product,
                        quantity=qty,
                        price=unit_price,
                        cost=product.cost,
                    )
                else:
                    suffix = f"комплект на {item.get('area') or '?'} м²"
                    DealItem.objects.create(
                        deal=deal,
                        custom_name=f"{item.get('product_name') or 'Товар'} — {suffix}"[:200],
                        quantity=qty,
                        price=unit_price,
                        cost=0,
                    )

            imported.event_uuid = event_uuid
            imported.payload = body
            imported.deal = deal
            imported.save(update_fields=["event_uuid", "payload", "deal"])
            log_activity("deal", deal.id, "Заказ с сайта", order_number, actor="Интернет-магазин")

        return Response({"ok": True, "duplicate": False, "deal_id": deal.id}, status=201)

    @staticmethod
    def _verify_signature(request):
        secret = settings.SHOP_WEBHOOK_SECRET
        timestamp = request.headers.get("X-Wallcov-Timestamp", "")
        signature = request.headers.get("X-Wallcov-Signature", "")
        if not secret or not timestamp.isdigit() or abs(int(time.time()) - int(timestamp)) > 300:
            return Response({"detail": "Подпись недействительна"}, status=403)
        expected = hmac.new(
            secret.encode(), timestamp.encode() + b"." + request.body, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return Response({"detail": "Подпись недействительна"}, status=403)
        return None

    @staticmethod
    def _normalise_phone(phone):
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) == 10 and digits.startswith("0"):
            digits = "38" + digits
        return "+" + digits

    @staticmethod
    def _delivery_label(order):
        return ", ".join(filter(None, [str(order.get("city") or ""), str(order.get("delivery_branch") or "")]))[:255]

    @staticmethod
    def _payment_label(method):
        return {
            "after_confirmation": "Після підтвердження менеджером",
            "cod": "Післяоплата НП",
            "online": "Онлайн-оплата",
        }.get(method, method[:40])

    @classmethod
    def _card_fields(cls, order):
        items = order.get("items") or []
        product_text = "; ".join(
            f"{item.get('product_name')} × {item.get('quantity', 1)}"
            for item in items
        )
        return [
            {"label": "Номер замовлення сайту", "value": order.get("number")},
            {"label": "Доставка", "value": cls._delivery_label(order)},
            {"label": "Товари", "value": product_text},
            {"label": "Коментар клієнта", "value": order.get("customer_comment") or "—"},
        ]


class EmailInvoicesTestView(APIView):
    """Перевірка зв'язку з поштовою скринькою накладних (Gmail IMAP).
    Читає провайдер email_invoices, підключається, рахує листи від відправників білого списку."""
    permission_classes = [ManagePerm]

    def post(self, request):
        import imaplib
        obj = IntegrationSettings.objects.filter(provider="email_invoices").first()
        cfg = (obj.config if obj else {}) or {}
        host = (cfg.get("imap_host") or "imap.gmail.com").strip()
        user = (cfg.get("email") or "").strip()
        pwd = (cfg.get("app_password") or "").strip()
        senders = [x.strip().lower() for x in re.split(r"[,;\s]+", cfg.get("senders") or "") if x.strip()]
        if not user or not pwd:
            return Response({"ok": False, "detail": "Заповни e-mail і пароль застосунку (app-password)"}, status=400)
        try:
            M = imaplib.IMAP4_SSL(host)
            M.login(user, pwd)
            M.select("INBOX", readonly=True)
            matched, samples = 0, []
            targets = senders or [None]
            for snd in targets:
                typ, data = (M.search(None, "FROM", '"%s"' % snd) if snd else M.search(None, "ALL"))
                ids = data[0].split() if (data and data[0]) else []
                matched += len(ids)
                for i in ids[-3:]:
                    typ, md = M.fetch(i, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                    if md and md[0]:
                        try:
                            raw = md[0][1].decode("utf-8", "ignore")
                        except Exception:
                            raw = str(md[0][1])
                        samples.append(" ".join(raw.split())[:160])
            M.logout()
            return Response({"ok": True, "host": host, "email": user, "senders": senders,
                             "matched": matched, "samples": samples[-6:]})
        except Exception as e:
            return Response({"ok": False, "detail": "Не вдалося підключитися: %s" % e}, status=400)


def _owner_only(request):
    u = request.user
    if not (u and u.is_authenticated and u.is_superuser):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("Розділ доступний тільки власнику")


class IncomingDocListView(APIView):
    """Список вхідних документів з пошти (чернетки). Тільки власник (superuser)."""
    def get(self, request):
        _owner_only(request)
        from .models import IncomingDoc
        st = request.query_params.get("status", "draft")
        qs = IncomingDoc.objects.all()
        if st:
            qs = qs.filter(status=st)
        out = []
        for d in qs[:300]:
            p = d.parsed or {}
            out.append({
                "id": d.id, "doc_type": d.doc_type, "status": d.status,
                "sender": d.sender, "subject": d.subject,
                "invoice_number": p.get("invoice_number"), "invoice_date": p.get("invoice_date"),
                "amount": p.get("amount"), "vat": p.get("vat"),
                "shipments_count": len(p.get("shipments") or []),
                "files": [a.get("name") for a in (d.attachments_b64 or [])] or p.get("files") or [],
                "email_date": p.get("email_date"),
                "created_payable": d.created_payable_id,
            })
        return Response(out)


class IncomingDocDetailView(APIView):
    """Деталі одного документа (рядки специфікації для звірки по сделкам)."""
    def get(self, request, pk):
        _owner_only(request)
        from .models import IncomingDoc
        from apps.crm.models import Deal
        d = IncomingDoc.objects.filter(id=pk).first()
        if not d:
            return Response({"detail": "не знайдено"}, status=404)
        p = d.parsed or {}
        if d.doc_type == "supplier":
            from .models import SupplierProductMap
            import re as _re
            m = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", d.sender or "")
            skey = (m.group(0).lower() if m else (d.sender or "").lower())
            lrows = []
            for ln in (p.get("lines") or []):
                tn = (ln.get("name") or "").strip()
                rule = SupplierProductMap.objects.filter(supplier_key=skey, their_name=tn).select_related("product").first()
                lrows.append({"their_name": tn, "qty": ln.get("qty"), "price": ln.get("price"), "sum": ln.get("sum"),
                              "product_id": (rule.product_id if rule else None),
                              "product_name": (rule.product.name if rule else "")})
            return Response({"id": d.id, "doc_type": "supplier", "status": d.status, "sender": d.sender,
                             "subject": d.subject, "invoice_number": p.get("invoice_number"),
                             "invoice_date": p.get("invoice_date"), "supplier": p.get("supplier"),
                             "amount": p.get("amount"), "lines": lrows})
        rows = []
        for s in (p.get("shipments") or []):
            deal = Deal.objects.filter(ttn=s.get("ttn")).first() if s.get("ttn") else None
            rows.append({"ttn": s.get("ttn"), "date": s.get("date"), "route": s.get("route"),
                         "cost": s.get("cost"),
                         "deal_id": deal.id if deal else None,
                         "deal_title": (getattr(deal, "title", "") or "")[:50] if deal else ""})
        return Response({"id": d.id, "doc_type": d.doc_type, "status": d.status,
                         "sender": d.sender, "subject": d.subject, "parsed": p, "shipments": rows})


class IncomingDocActionView(APIView):
    """confirm — провести (акт НП → кредиторка); reject — відхилити; delete — видалити."""
    def post(self, request, pk):
        _owner_only(request)
        from .models import IncomingDoc
        d = IncomingDoc.objects.filter(id=pk).first()
        if not d:
            return Response({"detail": "не знайдено"}, status=404)
        act = request.data.get("action")
        if act == "reject":
            d.status = "rejected"
            d.save(update_fields=["status"])
            return Response({"ok": True, "status": d.status})
        if act == "delete":
            d.delete()
            return Response({"ok": True, "deleted": True})
        if act == "confirm":
            if d.doc_type == "supplier":
                return _confirm_supplier(d, request)
            from apps.finance.np_act import create_kreditorka_from_act
            res = create_kreditorka_from_act(d.parsed or {}, request.user)
            if res.get("error"):
                return Response({"detail": "Не вдалося: %s" % res["error"]}, status=400)
            d.status = "confirmed"
            d.created_payable_id = res.get("payable_id")
            d.save(update_fields=["status", "created_payable"])
            return Response({"ok": True, "status": d.status, **res})
        return Response({"detail": "невідома дія"}, status=400)


class EmailInvoicesPollView(APIView):
    """Ручний запуск читання пошти (кнопка «Затягнути зараз»)."""
    permission_classes = [ManagePerm]

    def post(self, request):
        from .email_invoices import poll
        backfill = bool(request.data.get("backfill"))
        limit = int(request.data.get("limit") or 80)
        res = poll(limit=limit, backfill=backfill)
        return Response(res)


def _confirm_supplier(d, request):
    """Провести накладну постачальника: правила товарів + прихід на склад + кредиторка."""
    from apps.warehouse.models import StockDocument, StockMovement, Product, Warehouse
    from apps.crm.models import Contact
    from apps.finance.models import PlannedPayment
    from .models import SupplierProductMap
    from django.utils import timezone as _tz
    import datetime as _dt
    import re as _re

    p = d.parsed or {}
    lines = request.data.get("lines") or []
    if not lines:
        return Response({"detail": "Немає рядків для проведення"}, status=400)
    m = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", d.sender or "")
    skey = (m.group(0).lower() if m else (d.sender or "").lower())
    inv = p.get("invoice_number")
    if inv and StockDocument.objects.filter(kind="in", supplier_invoice=inv).exists():
        d.status = "confirmed"; d.save(update_fields=["status"])
        return Response({"ok": True, "already": True, "detail": "Прихід за цією накладною вже є"})
    wh = Warehouse.objects.filter(id=1).first() or Warehouse.objects.first()
    sup = p.get("supplier") or {}
    contact = None
    if sup.get("ipn"):
        contact = Contact.objects.filter(edrpou=sup["ipn"]).first()
    if not contact:
        contact = Contact.objects.filter(first_name__icontains="Корженевськ").first()
    if not contact and sup.get("name"):
        contact = Contact.objects.create(first_name=sup["name"][:120], edrpou=sup.get("ipn") or "", iban=sup.get("iban") or "")
    dd = None
    if p.get("invoice_date"):
        try:
            dd = _dt.datetime.strptime(p["invoice_date"], "%d.%m.%Y").date()
        except ValueError:
            dd = None
    doc = StockDocument.objects.create(
        kind="in", warehouse=wh, number=("Постач. %s" % (inv or ""))[:40], supplier=contact,
        supplier_invoice=(inv or "")[:80], doc_date=(dd or _tz.localdate()),
        author=(request.user if request.user.is_authenticated else None),
        comment=("Прихід від %s, накладна %s" % ((sup.get("name") or "постачальник"), inv or "?"))[:255])
    total = 0.0
    positions = rules = 0
    for ln in lines:
        pid = ln.get("product_id")
        if not pid:
            continue
        prod = Product.objects.filter(id=pid).first()
        if not prod:
            continue
        qty = ln.get("qty") or 0
        price = ln.get("price") or 0
        StockMovement.objects.create(document=doc, product=prod, quantity=qty, price=price)
        total += float(qty) * float(price)
        positions += 1
        tn = (ln.get("their_name") or "").strip()
        if tn:
            SupplierProductMap.objects.update_or_create(supplier_key=skey, their_name=tn, defaults={"product": prod})
            rules += 1
    amt = p.get("amount") or round(total, 2)
    pp = PlannedPayment.objects.create(
        kind="payable", amount=amt, due_date=(dd or _tz.localdate()),
        counterparty=(sup.get("name") or "Постачальник")[:160], contact=contact, status="planned",
        comment=("Постачальник · накладна %s від %s · %d позицій · ІПН %s"
                 % (inv or "?", p.get("invoice_date") or "?", positions, sup.get("ipn") or "?"))[:255])
    d.status = "confirmed"
    d.created_payable_id = pp.id
    d.save(update_fields=["status", "created_payable"])
    return Response({"ok": True, "stock_document_id": doc.id, "payable_id": pp.id,
                     "positions": positions, "rules_saved": rules, "amount": amt})
