# ============================================================================
#  Приёмник замера стен из приложения «Wallcov Замер» (iOS, LiDAR / RoomPlan).
#  POST /api/zamer/  — цепляет результат замера к сделке:
#     • в card_fields сделки (видно менеджеру прямо в карточке)
#     • в журнал ActivityLog (история действий)
#
#  Тело запроса (JSON), которое шлёт приложение:
#     { "deal_id": 123,
#       "walls": [{"width_cm":300,"height_cm":260}, ...],
#       "gross_m2": 21.4, "openings_m2": 3.2,
#       "net_m2": 18.2, "net_with_reserve_m2": 20.0 }
# ============================================================================
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.crm.models import Deal, log_activity

LABEL = "Замер стен (LiDAR)"
WALL_FUNNEL_ID = 5  # воронка «1.С/Покрытия для стен» — замер только для неё


class ZamerView(APIView):
    """Принять замер из iOS-приложения и прикрепить к сделке."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}

        # --- 0. Доступ к приложению замера (право zamer.access) ---
        u = request.user
        if not (u.is_superuser or "zamer.access" in u.effective_permissions()):
            return Response({"error": "Нет доступа к приложению замера. Обратитесь к руководителю."},
                            status=status.HTTP_403_FORBIDDEN)

        # --- 1. Найти сделку ---
        deal_id = data.get("deal_id")
        if not deal_id:
            return Response({"error": "deal_id обязателен"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            deal = Deal.objects.get(pk=int(deal_id))
        except (Deal.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Сделка не найдена"}, status=status.HTTP_404_NOT_FOUND)

        # --- 1b. Только воронка «Покрытия для стен» ---
        if deal.funnel_id != WALL_FUNNEL_ID:
            return Response({"error": "Замер только для воронки «Покрытия для стен»"},
                            status=status.HTTP_400_BAD_REQUEST)

        # --- 2. Разобрать цифры (безопасно) ---
        def num(key):
            try:
                return round(float(data.get(key) or 0), 1)
            except (ValueError, TypeError):
                return 0.0

        gross = num("gross_m2")
        openings = num("openings_m2")
        net = num("net_m2")
        reserve = num("net_with_reserve_m2")

        walls = data.get("walls") or []
        wall_lines = []
        for i, w in enumerate(walls, 1):
            try:
                ww = int(float(w.get("width_cm") or 0))
                hh = int(float(w.get("height_cm") or 0))
                wall_lines.append(f"Стена {i}: {ww}×{hh} см")
            except (ValueError, TypeError, AttributeError):
                continue

        # --- 3. Короткое значение для карточки сделки ---
        short = f"чисто {net} м² · с запасом +10% {reserve} м²"

        # --- 4. Полный текст для журнала ---
        detail = "; ".join(wall_lines)
        detail += f" | все стены {gross} м², минус проёмы {openings} м², чисто {net} м², +10% {reserve} м²"

        # --- 5. Записать в card_fields (заменить прошлый замер, если был) ---
        fields = deal.card_fields if isinstance(deal.card_fields, list) else []
        fields = [f for f in fields if not (isinstance(f, dict) and f.get("label") == LABEL)]
        fields.append({"label": LABEL, "value": short})
        deal.card_fields = fields
        deal.save(update_fields=["card_fields"])

        # --- 5b. План комнаты (картинка) → в фото сделки, видно в CRM ---
        plan = data.get("plan_png")
        if isinstance(plan, str) and plan.startswith("data:image"):
            photos = deal.ref_photos if isinstance(deal.ref_photos, list) else []
            photos.append(plan)
            deal.ref_photos = photos[-12:]      # не растим бесконечно
            deal.save(update_fields=["ref_photos"])

        # --- 6. Журнал ---
        log_activity("deal", deal.id, LABEL, detail=detail, user=request.user)

        return Response({"ok": True, "deal_id": deal.id, "deal_title": deal.title})


# ============================================================================
#  Регистрация клиента из приложения → создаёт ЛИД в CRM (воронка «Лиды»).
#  POST /api/zamer/register/  (без авторизации — публичный лид-кэптур)
#  Тело: {name, phone, city?, walls[], net_m2, net_with_reserve_m2,
#         gross_m2, openings_m2, perimeter_m, floor_m2}
#  Клиент, замеряющий стены у себя дома, попадает в CRM как лид с замером.
#  Учётные записи НЕ создаются (безопасно): дедуп контакта/лида по телефону.
# ============================================================================
from rest_framework.permissions import AllowAny
from django.utils import timezone
from datetime import timedelta
from apps.crm.models import Contact, Lead, Funnel, Stage

LEAD_FUNNEL_ID = 1   # воронка «Лиды»


class ClientRegisterZamerView(APIView):
    """Клиент из приложения регистрируется → создаётся лид + его замер в CRM."""
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data or {}
        name = (data.get("name") or "").strip()
        phone = "".join(ch for ch in (data.get("phone") or "") if ch.isdigit() or ch == "+")
        if len(phone.replace("+", "")) < 7:
            return Response({"error": "Укажите телефон"}, status=status.HTTP_400_BAD_REQUEST)
        if not name:
            name = "Клиент из приложения"

        def num(key):
            try:
                return round(float(data.get(key) or 0), 1)
            except (ValueError, TypeError):
                return 0.0
        net = num("net_m2"); reserve = num("net_with_reserve_m2")

        # --- контакт (дедуп по телефону) ---
        contact = Contact.objects.filter(phone=phone).first()
        if not contact:
            contact = Contact.objects.create(
                first_name=name[:120], phone=phone,
                source="app_zamer",
                address=(data.get("city") or "")[:255],
                comment="Пришёл из приложения «Wallcov Замер»",
            )

        # --- замер: короткая строка + разбивка по стенам ---
        short = f"чисто {net} м² · с запасом +10% {reserve} м²"
        walls = data.get("walls") or []
        wall_lines = []
        for i, w in enumerate(walls, 1):
            try:
                ww = int(float(w.get("width_cm") or 0)); hh = int(float(w.get("height_cm") or 0))
                wall_lines.append(f"Стена {i}: {ww}×{hh} см")
            except (ValueError, TypeError, AttributeError):
                continue
        detail = "; ".join(wall_lines)
        card = [
            {"label": "Замер стен (LiDAR)", "value": short},
            {"label": "Стены", "value": detail or "—"},
            {"label": "Длина по полу", "value": f"{num('perimeter_m')} м"},
            {"label": "Пол", "value": f"{num('floor_m2')} м²"},
        ]

        # --- дедуп лида: свежий лид (10 мин) по этому контакту — обновить, иначе создать ---
        recent = (Lead.objects.filter(contact=contact,
                                      created_at__gte=timezone.now() - timedelta(minutes=10))
                  .order_by("-created_at").first())
        if recent:
            recent.card_fields = card
            recent.save(update_fields=["card_fields"])
            lead = recent
        else:
            funnel = Funnel.objects.filter(pk=LEAD_FUNNEL_ID).first()
            if not funnel:
                return Response({"error": "Воронка лидов не найдена"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            stage = Stage.objects.filter(funnel=funnel).order_by("order", "id").first()
            if not stage:
                return Response({"error": "Нет стадий в воронке лидов"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            lead = Lead.objects.create(
                title=f"Замер из приложения — {name}"[:255],
                contact=contact, funnel=funnel, stage=stage,
                source="other", card_fields=card,
            )
            log_activity("lead", lead.id, "Замер стен (LiDAR)",
                         detail=f"{short}. {detail}", actor="Приложение (клиент)")

        return Response({"ok": True, "lead_id": lead.id})


# ============================================================================
#  Прайс для приложения «Wallcov Замер»: эффекты + материалы + инструменты.
#  GET /api/pricelist/  (без авторизации — клиенту тоже нужен для расчёта)
#  Эффекты/материалы — из живого Google-листа (файл effects.json, обновляет
#  крон build_effects.py). Инструменты — из каталога CRM (категория «1.6»).
# ============================================================================
import json as _json
from apps.warehouse.models import Product as _WHProduct

EFFECTS_JSON = "/app/warehouse_photos/pricelist/effects.json"
TOOLS_CATEGORY_ID = 63  # «1.6 ІНСТРУМЕНТИ»


class PricelistView(APIView):
    """Отдать прайс приложению: эффекты (авто-состав), материалы, инструменты."""
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with open(EFFECTS_JSON, encoding="utf-8") as f:
                data = _json.load(f)
        except Exception:
            data = {"effects": [], "materials": [], "generated_at": None}

        tools = []
        try:
            qs = (_WHProduct.objects
                  .filter(category_id=TOOLS_CATEGORY_ID, is_active=True)
                  .order_by("name"))
            tools = [{"id": p.id, "name": p.name,
                      "price": float(p.price or 0), "unit": p.unit or "шт"} for p in qs]
        except Exception:
            tools = []
        data["tools"] = tools
        return Response(data)
