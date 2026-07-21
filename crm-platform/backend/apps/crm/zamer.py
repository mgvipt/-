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

from apps.crm.models import Contact, Deal, Funnel, Stage, ZamerProject, log_activity

LABEL = "Замер стен (LiDAR)"
WALL_FUNNEL_ID = 5  # воронка «1.С/Покрытия для стен» — замер только для неё


class ZamerView(APIView):
    """Принять проект замера и смету строго для выбранного клиента.

    Новый контракт передаёт ``client_id`` и массив ``rooms``. CRM находит
    открытую сделку этого клиента в воронке покрытий или создаёт её. Старый
    контракт с ``deal_id`` и одной комнатой оставлен для совместимости.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}

        # --- 0. Доступ к приложению замера (право zamer.access) ---
        u = request.user
        if not (u.is_superuser or "zamer.access" in u.effective_permissions()):
            return Response({"error": "Нет доступа к приложению замера. Обратитесь к руководителю."},
                            status=status.HTTP_403_FORBIDDEN)

        def num(source, key):
            try:
                return round(float((source or {}).get(key) or 0), 2)
            except (ValueError, TypeError):
                return 0.0

        # --- 1. Определить выбранного клиента и не допустить смешивания ---
        deal = None
        deal_id = data.get("deal_id")
        if deal_id:
            try:
                deal = Deal.objects.select_related("contact", "stage").get(pk=int(deal_id))
            except (Deal.DoesNotExist, ValueError, TypeError):
                return Response({"error": "Сделка не найдена"}, status=status.HTTP_404_NOT_FOUND)
            if deal.funnel_id != WALL_FUNNEL_ID:
                return Response({"error": "Замер только для воронки «Покрытия для стен»"},
                                status=status.HTTP_400_BAD_REQUEST)

        client_id = data.get("client_id") or (deal.contact_id if deal else None)
        if not client_id:
            return Response({"error": "Сначала выберите клиента в проекте замера"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            contact = Contact.objects.get(pk=int(client_id))
        except (Contact.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Выбранный клиент не найден"}, status=status.HTTP_404_NOT_FOUND)
        if deal and deal.contact_id != contact.id:
            return Response({"error": "Эта сделка принадлежит другому клиенту"},
                            status=status.HTTP_409_CONFLICT)

        # --- 2. Комнаты: новый массив или одна legacy-комната ---
        rooms = data.get("rooms") if isinstance(data.get("rooms"), list) else []
        if not rooms:
            rooms = [{
                "name": data.get("room_name") or "Комната 1",
                "walls": data.get("walls") or [],
                "openings": data.get("openings") or [],
                "gross_m2": data.get("gross_m2"),
                "openings_m2": data.get("openings_m2"),
                "net_m2": data.get("net_m2"),
                "net_with_reserve_m2": data.get("net_with_reserve_m2"),
                "perimeter_m": data.get("perimeter_m"),
                "floor_m2": data.get("floor_m2"),
                "ceiling_m2": data.get("ceiling_m2"),
                "reveals_linear_m": data.get("reveals_linear_m"),
                "reveals_area_m2": data.get("reveals_area_m2"),
            }]

        clean_rooms = []
        for index, room in enumerate(rooms, 1):
            if not isinstance(room, dict):
                continue
            walls = room.get("walls") if isinstance(room.get("walls"), list) else []
            openings = room.get("openings") if isinstance(room.get("openings"), list) else []
            clean_rooms.append({
                "name": str(room.get("name") or f"Комната {index}")[:120],
                "walls": walls,
                "openings": openings,
                "gross_m2": num(room, "gross_m2"),
                "openings_m2": num(room, "openings_m2"),
                "net_m2": num(room, "net_m2"),
                "net_with_reserve_m2": num(room, "net_with_reserve_m2"),
                "perimeter_m": num(room, "perimeter_m"),
                "floor_m2": num(room, "floor_m2"),
                "ceiling_m2": num(room, "ceiling_m2"),
                "reveals_linear_m": num(room, "reveals_linear_m"),
                "reveals_area_m2": num(room, "reveals_area_m2"),
            })
        if not clean_rooms:
            return Response({"error": "В проекте нет комнат для отправки"},
                            status=status.HTTP_400_BAD_REQUEST)

        totals = {
            key: round(sum(float(room.get(key) or 0) for room in clean_rooms), 2)
            for key in ("gross_m2", "openings_m2", "net_m2", "net_with_reserve_m2",
                        "perimeter_m", "floor_m2", "ceiling_m2",
                        "reveals_linear_m", "reveals_area_m2")
        }

        # --- 3. Сделка только выбранного клиента: найти или создать ---
        if not deal:
            deal = (Deal.objects.select_related("stage")
                    .filter(contact=contact, funnel_id=WALL_FUNNEL_ID,
                            stage__is_won=False, stage__is_lost=False)
                    .order_by("-updated_at", "-id").first())
        if not deal:
            funnel = Funnel.objects.filter(pk=WALL_FUNNEL_ID).first()
            first_stage = (Stage.objects.filter(funnel_id=WALL_FUNNEL_ID, auto_only=False)
                           .order_by("order", "id").first())
            if not funnel or not first_stage:
                return Response({"error": "Воронка замера не настроена"},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            deal = Deal.objects.create(
                title=f"Замер · {contact}"[:255], contact=contact,
                funnel=funnel, stage=first_stage, source="other", owner=request.user,
            )

        # --- 4. Читаемая разбивка по комнатам для карточки и журнала ---
        room_lines = []
        for room in clean_rooms:
            wall_sizes = []
            for wall_index, wall in enumerate(room["walls"], 1):
                if not isinstance(wall, dict):
                    continue
                try:
                    wall_sizes.append(
                        f"С{wall_index} {int(float(wall.get('width_cm') or 0))}×"
                        f"{int(float(wall.get('height_cm') or 0))} см"
                    )
                except (ValueError, TypeError):
                    continue
            line = (
                f"{room['name']}: стены {room['net_m2']} м², пол {room['floor_m2']} м², "
                f"потолок {room['ceiling_m2']} м², откосы {room['reveals_linear_m']} м.п. / "
                f"{room['reveals_area_m2']} м²"
            )
            if wall_sizes:
                line += " · " + ", ".join(wall_sizes)
            room_lines.append(line)

        project_uuid = str(data.get("project_uuid") or "legacy")[:64]
        measurement_label = f"Замер Wallcov · {project_uuid}"
        short = (f"{len(clean_rooms)} комн. · стены {totals['net_m2']} м² · "
                 f"пол/потолок {totals['floor_m2']} м² · откосы {totals['reveals_linear_m']} м.п.")

        # --- 5. В карточке сделки обновляется только проект этого клиента ---
        fields = deal.card_fields if isinstance(deal.card_fields, list) else []
        fields = [f for f in fields if not (
            isinstance(f, dict) and f.get("label") in (LABEL, measurement_label)
        )]
        fields.append({"label": measurement_label, "value": short + "\n" + "\n".join(room_lines)})

        estimate = data.get("estimate") if isinstance(data.get("estimate"), dict) else {}
        estimate_total = num(estimate, "total")
        if estimate:
            estimate_label = f"Смета Wallcov · {project_uuid}"
            fields = [f for f in fields if not (isinstance(f, dict) and f.get("label") == estimate_label)]
            estimate_lines = estimate.get("lines") if isinstance(estimate.get("lines"), list) else []
            positions = []
            for line in estimate_lines[:80]:
                if not isinstance(line, dict):
                    continue
                positions.append(
                    f"{line.get('role') or 'Позиция'}: {line.get('title') or '—'} · "
                    f"{num(line, 'quantity')} {line.get('unit') or ''} · {num(line, 'cost')} грн"
                )
            estimate_value = f"Площадь {num(estimate, 'area_m2')} м² · итого {estimate_total} грн"
            if positions:
                estimate_value += "\n" + "\n".join(positions)
            fields.append({"label": estimate_label, "value": estimate_value})
            if estimate_total > 0:
                deal.amount = estimate_total

        deal.card_fields = fields
        deal.save(update_fields=["card_fields", "amount", "updated_at"])

        # --- 6. План комнаты → фото сделки ---
        plan = data.get("plan_png")
        if isinstance(plan, str) and plan.startswith("data:image"):
            photos = deal.ref_photos if isinstance(deal.ref_photos, list) else []
            photos.append(plan)
            deal.ref_photos = photos[-12:]      # не растим бесконечно
            deal.save(update_fields=["ref_photos"])

        # --- 7. Канонический проект для карточки конкретного клиента ---
        device_uuid = str(data.get("device_uuid") or f"crm-user-{request.user.id}")[:64]
        project_payload = {
            "id": project_uuid,
            "clientId": contact.id,
            "clientName": str(contact),
            "rooms": clean_rooms,
            "totals": totals,
            "estimate": estimate,
            "dealId": deal.id,
        }
        ZamerProject.objects.update_or_create(
            device_uuid=device_uuid, project_uuid=project_uuid,
            defaults={"title": str(data.get("project_name") or contact)[:255],
                      "payload": project_payload, "user": request.user},
        )

        detail = "\n".join(room_lines)
        if estimate:
            detail += f"\nСмета: {estimate_total} грн"
        log_activity("deal", deal.id, "Замер и смета Wallcov", detail=detail, user=request.user)

        return Response({"ok": True, "deal_id": deal.id, "deal_title": deal.title,
                         "client_id": contact.id, "rooms_count": len(clean_rooms),
                         "totals": totals})


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
from apps.crm.models import Lead

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


# ============================================================================
#  Проекты замера (устойчивое хранение) — чтобы не терялись после
#  переустановки/переделки приложения. Привязка к устройству (device_uuid
#  из Keychain) и к пользователю (если вошёл).
#  GET  /api/zamer/projects/?device_uuid=...            → список проектов
#  POST /api/zamer/projects/  {device_uuid, project_uuid, title, payload}  → upsert
#  DELETE /api/zamer/projects/?device_uuid=&project_uuid=                  → удалить
# ============================================================================
class ZamerProjectsView(APIView):
    permission_classes = [AllowAny]

    def _user(self, request):
        u = getattr(request, "user", None)
        return u if (u is not None and getattr(u, "is_authenticated", False)) else None

    def get(self, request):
        dev = (request.query_params.get("device_uuid") or "").strip()
        user = self._user(request)
        if not dev and not user:
            return Response([])
        from django.db.models import Q as _Q
        q = _Q()
        if dev:  q |= _Q(device_uuid=dev)
        if user: q |= _Q(user=user)
        rows = ZamerProject.objects.filter(q)
        return Response([{
            "project_uuid": p.project_uuid,
            "title": p.title,
            "payload": p.payload,
            "updated_at": p.updated_at.isoformat(),
        } for p in rows])

    def post(self, request):
        d = request.data or {}
        dev = (d.get("device_uuid") or "").strip()
        pu = (d.get("project_uuid") or "").strip()
        if not dev or not pu:
            return Response({"error": "device_uuid и project_uuid обязательны"},
                            status=status.HTTP_400_BAD_REQUEST)
        obj, _ = ZamerProject.objects.update_or_create(
            device_uuid=dev, project_uuid=pu,
            defaults={"title": (d.get("title") or "")[:255],
                      "payload": d.get("payload") or {},
                      "user": self._user(request)})
        return Response({"ok": True, "project_uuid": obj.project_uuid})

    def delete(self, request):
        dev = (request.query_params.get("device_uuid") or "").strip()
        pu = (request.query_params.get("project_uuid") or "").strip()
        if dev and pu:
            ZamerProject.objects.filter(device_uuid=dev, project_uuid=pu).delete()
        return Response({"ok": True})
