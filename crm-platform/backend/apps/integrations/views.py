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
from .models import IntegrationSettings, ShopOrderImport
from . import adapters

PROVIDERS = {
    "liqpay": ["public_key", "private_key", "currency"],
    "checkbox": ["token", "license_key"],
    "novaposhta": ["api_key", "sender_ref", "sender_city_ref", "sender_contact", "sender_phone"],
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

        all_samples = all(str(item.get("type")) == "sample" for item in items)
        funnel_name = "22 Тестовий набір" if all_samples else "21 Основний продукт"
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
            for item, qty, unit_price in normalised_items:
                suffix = "пробник" if item.get("type") == "sample" else f"комплект на {item.get('area') or '?'} м²"
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
