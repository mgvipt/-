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

from apps.crm.models import (
    CalcSettings, Contact, Deal, Estimate, Funnel, Stage, ZamerProject,
    default_calc_settings, log_activity,
)
from django.db import transaction
from django.db.models import Q
import math

LABEL = "Замер стен (LiDAR)"
WALL_FUNNEL_ID = 5  # воронка «1.С/Покрытия для стен» — замер только для неё


def visible_contacts(user):
    """Тот же клиентский scope, что и в основном ContactViewSet."""
    qs = Contact.objects.all()
    if not (user.is_superuser or user.can_see_all_clients()):
        qs = qs.filter(
            Q(owner=user) | Q(leads__owner=user) | Q(deals__owner=user) | Q(shared_with=user)
        ).distinct()
    allowed_kinds = user.allowed_contact_kinds()
    if allowed_kinds is not None:
        kind_scope = Q(kinds=[])
        for kind in allowed_kinds:
            kind_scope |= Q(kinds__contains=[kind])
        qs = qs.filter(kind_scope)
    return qs


def visible_deals(user):
    """Повторяет responsibility/funnel scope основного DealViewSet."""
    qs = Deal.objects.select_related("contact", "stage")
    if user.is_superuser or user.can_see_all_deals():
        return qs
    allowed = user.allowed_funnel_ids()
    if allowed is not None:
        qs = qs.filter(funnel_id__in=allowed)
    shared_stage_ids = user.viewable_all_stage_ids()
    if shared_stage_ids:
        qs = qs.filter(
            Q(owner=user)
            | Q(stage_id__in=list(shared_stage_ids))
            | Q(owner__isnull=True, stage__order=0)
        )
    else:
        qs = qs.filter(Q(owner=user) | Q(owner__isnull=True, stage__order=0))
    return qs.distinct()


def has_code(user, code):
    return bool(user.is_superuser or user.has_perm_code(code))


def can_edit_deal(user, deal):
    return bool(
        user.is_superuser
        or has_code(user, "deal.edit.all")
        or deal.owner_id in (None, user.id)
    )


def account_project(user, device_uuid, project_uuid):
    """Найти проект аккаунта, не позволяя забрать UUID общего устройства."""
    exact = ZamerProject.objects.filter(
        device_uuid=device_uuid, project_uuid=project_uuid,
    ).first()
    if exact is not None:
        if exact.user_id not in (None, user.id):
            return None, "Проект принадлежит другому аккаунту"
        return exact, None
    own = ZamerProject.objects.filter(user=user, project_uuid=project_uuid).first()
    return own, None


class ZamerView(APIView):
    """Принять проект замера и смету строго для выбранного клиента.

    Новый контракт передаёт ``client_id`` и массив ``rooms``. CRM находит
    открытую сделку этого клиента в воронке покрытий или создаёт её. Старый
    контракт с ``deal_id`` и одной комнатой оставлен для совместимости.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > 12_000_000:
            return Response({"error": "Файл замера слишком большой"},
                            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        data = request.data or {}

        # --- 0. Доступ к приложению замера (право zamer.access) ---
        u = request.user
        if not (u.is_superuser or "zamer.access" in u.effective_permissions()):
            return Response({"error": "Нет доступа к приложению замера. Обратитесь к руководителю."},
                            status=status.HTTP_403_FORBIDDEN)
        allowed_funnels = u.allowed_funnel_ids()
        if allowed_funnels is not None and WALL_FUNNEL_ID not in allowed_funnels:
            return Response({"error": "Нет доступа к воронке «Покрытия для стен»"},
                            status=status.HTTP_403_FORBIDDEN)

        def num(source, key):
            try:
                value = float((source or {}).get(key) or 0)
            except (ValueError, TypeError):
                return 0.0
            if not math.isfinite(value):
                return 0.0
            return round(min(max(value, 0.0), 1_000_000_000.0), 2)

        # --- 1. Определить выбранного клиента и не допустить смешивания ---
        deal = None
        deal_id = data.get("deal_id")
        if deal_id:
            try:
                deal = visible_deals(u).get(pk=int(deal_id))
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
            contact = visible_contacts(u).get(pk=int(client_id))
        except (Contact.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Выбранный клиент не найден"}, status=status.HTTP_404_NOT_FOUND)
        if deal and deal.contact_id != contact.id:
            return Response({"error": "Эта сделка принадлежит другому клиенту"},
                            status=status.HTTP_409_CONFLICT)
        if deal and not can_edit_deal(u, deal):
            return Response({"error": "Нет права изменять сделку другого ответственного"},
                            status=status.HTTP_403_FORBIDDEN)

        # Проверяем account ownership проекта до создания сделки и любых записей.
        device_uuid = str(data.get("device_uuid") or f"crm-user-{u.id}").strip()
        provided_project_uuid = str(data.get("project_uuid") or "").strip()
        if len(device_uuid) > 64 or len(provided_project_uuid) > 64:
            return Response({"error": "Некорректный идентификатор проекта"},
                            status=status.HTTP_400_BAD_REQUEST)
        project_uuid = provided_project_uuid
        project = None
        if project_uuid:
            project, project_error = account_project(u, device_uuid, project_uuid)
            if project_error:
                return Response({"error": project_error}, status=status.HTTP_409_CONFLICT)
            if project is not None:
                payload = project.payload if isinstance(project.payload, dict) else {}
                payload_contact_id = payload.get("clientId") or payload.get("client_id")
                if project.contact_id not in (None, contact.id):
                    return Response({"error": "Проект уже привязан к другому клиенту"},
                                    status=status.HTTP_409_CONFLICT)
                try:
                    if payload_contact_id and int(payload_contact_id) != contact.id:
                        return Response({"error": "В проекте сохранён другой клиент"},
                                        status=status.HTTP_409_CONFLICT)
                except (TypeError, ValueError):
                    return Response({"error": "В проекте некорректный идентификатор клиента"},
                                    status=status.HTTP_409_CONFLICT)
                if deal is None and project.deal_id:
                    deal = visible_deals(u).filter(pk=project.deal_id).first()
                    if deal is None or not can_edit_deal(u, deal):
                        return Response({"error": "Сделка проекта недоступна этому сотруднику"},
                                        status=status.HTTP_403_FORBIDDEN)
                    if deal.funnel_id != WALL_FUNNEL_ID or deal.contact_id != contact.id:
                        return Response({"error": "В проекте сохранена сделка другого клиента"},
                                        status=status.HTTP_409_CONFLICT)

        # --- 2. Комнаты: новый массив или одна legacy-комната ---
        if "rooms" in data:
            if not isinstance(data.get("rooms"), list) or not data.get("rooms"):
                return Response({"error": "В проекте нет комнат для отправки"},
                                status=status.HTTP_400_BAD_REQUEST)
            rooms = data["rooms"]
        else:
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
        for index, room in enumerate(rooms[:200], 1):
            if not isinstance(room, dict):
                continue
            walls = (room.get("walls") if isinstance(room.get("walls"), list) else [])[:500]
            openings = (room.get("openings") if isinstance(room.get("openings"), list) else [])[:500]
            wall_segments = (
                room.get("wall_segments") if isinstance(room.get("wall_segments"), list) else []
            )[:500]
            extra_measures = (
                room.get("extra_measures") if isinstance(room.get("extra_measures"), list) else []
            )[:500]
            clean_rooms.append({
                "room_uuid": str(room.get("room_uuid") or "")[:64],
                "name": str(room.get("name") or f"Комната {index}")[:120],
                "walls": walls,
                "wall_segments": wall_segments,
                "openings": openings,
                "extra_measures": extra_measures,
                "geometry": room.get("geometry") if isinstance(room.get("geometry"), dict) else {},
                "structures": (room.get("structures") if isinstance(room.get("structures"), list) else [])[:500],
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

        # Смета — отдельное защищённое действие; нельзя подделать её одним
        # только правом замера и тем самым изменить сумму сделки.
        raw_estimate = data.get("estimate") if isinstance(data.get("estimate"), dict) else {}
        estimate = {}
        if raw_estimate:
            if not has_code(u, "calc.access"):
                return Response({"error": "Нет доступа к калькулятору смет"},
                                status=status.HTTP_403_FORBIDDEN)
            clean_lines = []
            raw_lines = raw_estimate.get("lines") if isinstance(raw_estimate.get("lines"), list) else []
            for line in raw_lines[:500]:
                if not isinstance(line, dict):
                    continue
                clean_lines.append({
                    "title": str(line.get("title") or "")[:255],
                    "role": str(line.get("role") or "")[:120],
                    "quantity": num(line, "quantity"),
                    "unit": str(line.get("unit") or "")[:32],
                    "cost": num(line, "cost"),
                })
            estimate = {
                "area_m2": num(raw_estimate, "area_m2"),
                "subtotal": num(raw_estimate, "subtotal"),
                "discount": num(raw_estimate, "discount"),
                "total": num(raw_estimate, "total"),
                "lines": clean_lines,
            }

        # --- 3. Сделка только выбранного клиента: найти или создать ---
        if not deal:
            editable = visible_deals(u).filter(
                contact=contact, funnel_id=WALL_FUNNEL_ID,
                stage__is_won=False, stage__is_lost=False,
            )
            if not has_code(u, "deal.edit.all"):
                editable = editable.filter(Q(owner=u) | Q(owner__isnull=True))
            deal = editable.order_by("-updated_at", "-id").first()
        if not deal:
            foreign_open = Deal.objects.filter(
                contact=contact, funnel_id=WALL_FUNNEL_ID,
                stage__is_won=False, stage__is_lost=False,
            ).exists()
            if foreign_open:
                return Response({"error": "У клиента уже есть открытая сделка другого ответственного"},
                                status=status.HTTP_403_FORBIDDEN)
            if not (has_code(u, "zamer.deal.create") or has_code(u, "deal.create")):
                return Response({"error": "Нет права создавать сделку из приложения замера"},
                                status=status.HTTP_403_FORBIDDEN)
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

        # Для legacy-контракта отдельный UUID на сделку, иначе все старые
        # замеры пользователя попадали бы в один проект ``legacy``.
        if not project_uuid:
            project_uuid = f"legacy-deal-{deal.id}"
            project, project_error = account_project(u, device_uuid, project_uuid)
            if project_error:
                return Response({"error": project_error}, status=status.HTTP_409_CONFLICT)
        if project is not None:
            if project.contact_id not in (None, contact.id):
                return Response({"error": "Проект уже привязан к другому клиенту"},
                                status=status.HTTP_409_CONFLICT)
            if project.deal_id not in (None, deal.id):
                return Response({"error": "Проект уже привязан к другой сделке"},
                                status=status.HTTP_409_CONFLICT)
        else:
            project = ZamerProject(
                user=u, device_uuid=device_uuid, project_uuid=project_uuid, revision=0,
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

        measurement_label = f"Замер Wallcov · {project_uuid}"
        short = (f"{len(clean_rooms)} комн. · стены {totals['net_m2']} м² · "
                 f"пол/потолок {totals['floor_m2']} м² · откосы {totals['reveals_linear_m']} м.п.")

        # --- 5. В карточке сделки обновляется только проект этого клиента ---
        fields = deal.card_fields if isinstance(deal.card_fields, list) else []
        fields = [f for f in fields if not (
            isinstance(f, dict) and f.get("label") in (LABEL, measurement_label)
        )]
        fields.append({"label": measurement_label, "value": short + "\n" + "\n".join(room_lines)})

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
        project_payload = {
            "id": project_uuid,
            "clientId": contact.id,
            "clientName": str(contact),
            "rooms": clean_rooms,
            "totals": totals,
            "estimate": estimate,
            "dealId": deal.id,
        }
        is_new_project = project.pk is None
        project.user = u
        project.device_uuid = device_uuid
        project.contact = contact
        project.deal = deal
        project.title = str(data.get("project_name") or contact)[:255]
        project.payload = project_payload
        project.revision = 1 if is_new_project else int(project.revision or 0) + 1
        project.save()

        # --- 8. Нативная смета CRM: тот же клиент, проект и ответственное лицо ---
        estimate_obj = None
        if estimate:
            estimate_obj = Estimate.objects.filter(project=project, deal=deal).first()
            is_new_estimate = estimate_obj is None
            estimate_totals = {
                "area_m2": num(estimate, "area_m2"),
                "subtotal": num(estimate, "subtotal"),
                "discount": num(estimate, "discount"),
                "total": estimate_total,
                "measurement": totals,
            }
            if is_new_estimate:
                estimate_obj = Estimate(project=project, deal=deal, contact=contact, owner=u)
            estimate_obj.name = str(data.get("project_name") or f"Смета · {contact}")[:255]
            estimate_obj.contact = contact
            estimate_obj.deal = deal
            estimate_obj.owner = u
            estimate_obj.measurement_snapshot = {
                "project_uuid": project_uuid, "rooms": clean_rooms, "totals": totals,
            }
            estimate_obj.lines = estimate.get("lines") if isinstance(estimate.get("lines"), list) else []
            estimate_obj.totals = estimate_totals
            estimate_obj.version = 1 if is_new_estimate else int(estimate_obj.version or 0) + 1
            estimate_obj.save()

        detail = "\n".join(room_lines)
        if estimate:
            detail += f"\nСмета: {estimate_total} грн"
        log_activity("deal", deal.id, "Замер и смета Wallcov", detail=detail, user=request.user)

        return Response({"ok": True, "deal_id": deal.id, "deal_title": deal.title,
                         "client_id": contact.id, "rooms_count": len(clean_rooms),
                         "totals": totals,
                         "project_id": project.id, "project_revision": project.revision,
                         "estimate_id": estimate_obj.id if estimate_obj else None,
                         "calculator_url": request.build_absolute_uri(
                             f"/deals/{deal.id}?tab=smeta"
                         )})


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
    permission_classes = [IsAuthenticated]

    def _user(self, request):
        u = getattr(request, "user", None)
        return u if (u is not None and getattr(u, "is_authenticated", False)) else None

    def get(self, request):
        user = self._user(request)
        if not user or not has_code(user, "zamer.access"):
            return Response({"detail": "Нет доступа к проектам замера"},
                            status=status.HTTP_403_FORBIDDEN)
        rows = ZamerProject.objects.filter(user=user)
        client_id = request.query_params.get("client_id")
        if client_id:
            try:
                rows = rows.filter(contact_id=int(client_id))
            except (TypeError, ValueError):
                return Response({"detail": "Некорректный client_id"},
                                status=status.HTTP_400_BAD_REQUEST)
        return Response([{
            "project_uuid": p.project_uuid,
            "title": p.title,
            "payload": p.payload,
            "client_id": p.contact_id,
            "deal_id": p.deal_id,
            "revision": p.revision,
            "updated_at": p.updated_at.isoformat(),
        } for p in rows])

    def post(self, request):
        d = request.data or {}
        dev = (d.get("device_uuid") or "").strip()
        pu = (d.get("project_uuid") or "").strip()
        user = self._user(request)
        if not user or not has_code(user, "zamer.access"):
            return Response({"detail": "Нет доступа к проектам замера"},
                            status=status.HTTP_403_FORBIDDEN)
        if not dev or not pu:
            return Response({"error": "device_uuid и project_uuid обязательны"},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(dev) > 64 or len(pu) > 64:
            return Response({"error": "Некорректный идентификатор проекта"},
                            status=status.HTTP_400_BAD_REQUEST)
        payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        contact_id = payload.get("clientId") or d.get("client_id")
        contact = None
        if contact_id:
            try:
                contact = visible_contacts(user).get(pk=int(contact_id))
            except (Contact.DoesNotExist, ValueError, TypeError):
                return Response({"error": "Клиент недоступен этому сотруднику"},
                                status=status.HTTP_404_NOT_FOUND)
        obj, project_error = account_project(user, dev, pu)
        if project_error:
            return Response({"error": project_error}, status=status.HTTP_409_CONFLICT)
        if obj is None:
            obj = ZamerProject(user=user, device_uuid=dev, project_uuid=pu, revision=0)
        elif obj.contact_id and contact is not None and obj.contact_id != contact.id:
            return Response({"error": "Проект уже привязан к другому клиенту"},
                            status=status.HTTP_409_CONFLICT)
        elif contact is None:
            contact = obj.contact

        deal = obj.deal
        deal_id = payload.get("dealId") or d.get("deal_id")
        if deal_id:
            try:
                candidate = visible_deals(user).get(pk=int(deal_id))
            except (Deal.DoesNotExist, ValueError, TypeError):
                return Response({"error": "Сделка недоступна этому сотруднику"},
                                status=status.HTTP_404_NOT_FOUND)
            if contact is not None and candidate.contact_id != contact.id:
                return Response({"error": "Сделка принадлежит другому клиенту"},
                                status=status.HTTP_409_CONFLICT)
            if deal is not None and deal.id != candidate.id:
                return Response({"error": "Проект уже привязан к другой сделке"},
                                status=status.HTTP_409_CONFLICT)
            deal = candidate
        is_new_project = obj.pk is None
        obj.user = user
        obj.device_uuid = dev
        obj.title = (d.get("title") or "")[:255]
        obj.payload = payload
        obj.contact = contact
        obj.deal = deal
        obj.revision = 1 if is_new_project else int(obj.revision or 0) + 1
        obj.save()
        return Response({"ok": True, "project_uuid": obj.project_uuid, "revision": obj.revision})

    def delete(self, request):
        pu = (request.query_params.get("project_uuid") or "").strip()
        user = self._user(request)
        if not user or not has_code(user, "zamer.access"):
            return Response({"detail": "Нет доступа к проектам замера"},
                            status=status.HTTP_403_FORBIDDEN)
        if not pu:
            return Response({"error": "project_uuid обязателен"},
                            status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = ZamerProject.objects.filter(user=user, project_uuid=pu).delete()
        return Response({"ok": True, "deleted": deleted})


class CalcSettingsView(APIView):
    permission_classes = [IsAuthenticated]
    NUMERIC_LIMITS = {
        "reserve_pct": (0, 100), "labor_wall_m2": (0, 100000),
        "labor_reveal_linear_m": (0, 100000), "material_reveal_m2": (0, 100000),
        "transport_per_km": (0, 100000), "transport_min": (0, 1000000),
        "minimum_order": (0, 10000000), "overhead_pct": (0, 100),
        "max_discount_pct": (0, 100), "rounding_step": (0.01, 10000),
    }

    def _can_manage(self, user):
        return has_code(user, "calc.settings.manage") or has_code(user, "roles.manage")

    @staticmethod
    def _stored_values(obj):
        saved = obj.values if isinstance(obj.values, dict) else {}
        return {**default_calc_settings(), **saved}

    def get(self, request):
        if not (self._can_manage(request.user) or has_code(request.user, "calc.access")):
            return Response({"detail": "Нет доступа к калькулятору"},
                            status=status.HTTP_403_FORBIDDEN)
        obj, _ = CalcSettings.objects.get_or_create(key="default")
        # Полный набор ставок нужен калькулятору сотрудника для расчёта.
        # Гость/клиент этот защищённый endpoint вызвать не может, а менять
        # значения по-прежнему разрешено только администратору/делегату.
        values = self._stored_values(obj)
        return Response({"values": values, "can_manage": self._can_manage(request.user),
                         "updated_at": obj.updated_at.isoformat()})

    def patch(self, request):
        if not self._can_manage(request.user):
            return Response({"detail": "Настройки доступны только администратору или ответственному"},
                            status=status.HTTP_403_FORBIDDEN)
        incoming = request.data.get("values") if isinstance(request.data.get("values"), dict) else request.data
        if not isinstance(incoming, dict):
            return Response({"detail": "Ожидается объект values"},
                            status=status.HTTP_400_BAD_REQUEST)
        obj, _ = CalcSettings.objects.get_or_create(key="default")
        values = self._stored_values(obj)
        for key, (minimum, maximum) in self.NUMERIC_LIMITS.items():
            if key not in incoming:
                continue
            try:
                if isinstance(incoming[key], bool):
                    raise ValueError
                value = float(incoming[key])
            except (TypeError, ValueError):
                return Response({"detail": f"Некорректное значение: {key}"},
                                status=status.HTTP_400_BAD_REQUEST)
            if not minimum <= value <= maximum:
                return Response({"detail": f"Значение {key} вне допустимого диапазона"},
                                status=status.HTTP_400_BAD_REQUEST)
            values[key] = value
        if "show_internal_rates_to_client" in incoming:
            if not isinstance(incoming["show_internal_rates_to_client"], bool):
                return Response({"detail": "show_internal_rates_to_client должен быть true или false"},
                                status=status.HTTP_400_BAD_REQUEST)
            values["show_internal_rates_to_client"] = incoming["show_internal_rates_to_client"]
        if "reveal_sides" in incoming:
            if not isinstance(incoming["reveal_sides"], list):
                return Response({"detail": "reveal_sides должен быть списком"},
                                status=status.HTTP_400_BAD_REQUEST)
            valid_sides = {"left", "right", "top", "bottom"}
            if any(
                not isinstance(side, str) or side not in valid_sides
                for side in incoming["reveal_sides"]
            ):
                return Response({"detail": "Некорректная сторона откоса"},
                                status=status.HTTP_400_BAD_REQUEST)
            values["reveal_sides"] = list(dict.fromkeys(incoming["reveal_sides"]))
        obj.values = values
        obj.updated_by = request.user
        obj.save()
        return Response({"values": values, "can_manage": True,
                         "updated_at": obj.updated_at.isoformat()})


class EstimateView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _can_access(user):
        return has_code(user, "calc.access") or has_code(user, "deal.smeta.tab")

    @staticmethod
    def _can_edit(user, row):
        return bool(
            has_code(user, "calc.edit.all")
            or row.owner_id == user.id
            or (row.deal_id is not None and row.deal.owner_id == user.id)
        )

    def _queryset(self, user):
        qs = Estimate.objects.select_related("contact", "deal", "project", "owner")
        if has_code(user, "calc.view.all"):
            return qs
        return qs.filter(
            contact_id__in=visible_contacts(user).values("pk"),
        ).filter(
            Q(deal_id__in=visible_deals(user).values("pk"))
            | Q(deal__isnull=True, owner=user)
        ).distinct()

    def get(self, request, pk=None):
        if not self._can_access(request.user):
            return Response({"detail": "Нет доступа к сметам"}, status=status.HTTP_403_FORBIDDEN)
        qs = self._queryset(request.user)
        if pk is not None:
            row = qs.filter(pk=pk).first()
            if not row:
                return Response({"detail": "Смета не найдена"}, status=status.HTTP_404_NOT_FOUND)
            return Response(self._serialize(row, request.user))
        if request.query_params.get("deal_id"):
            try:
                qs = qs.filter(deal_id=int(request.query_params["deal_id"]))
            except (TypeError, ValueError):
                return Response({"detail": "Некорректный deal_id"},
                                status=status.HTTP_400_BAD_REQUEST)
        if request.query_params.get("contact_id"):
            try:
                qs = qs.filter(contact_id=int(request.query_params["contact_id"]))
            except (TypeError, ValueError):
                return Response({"detail": "Некорректный contact_id"},
                                status=status.HTTP_400_BAD_REQUEST)
        if request.query_params.get("project_uuid"):
            qs = qs.filter(project__project_uuid=request.query_params["project_uuid"])
        return Response([self._serialize(row, request.user) for row in qs[:200]])

    def patch(self, request, pk=None):
        if not self._can_access(request.user):
            return Response({"detail": "Нет доступа к сметам"}, status=status.HTTP_403_FORBIDDEN)
        if pk is None:
            return Response({"detail": "Не указана смета"}, status=status.HTTP_400_BAD_REQUEST)
        row = self._queryset(request.user).filter(pk=pk).first()
        if not row:
            return Response({"detail": "Смета не найдена"}, status=status.HTTP_404_NOT_FOUND)
        if not self._can_edit(request.user, row):
            return Response({"detail": "Можно редактировать только свою смету"},
                            status=status.HTTP_403_FORBIDDEN)
        if "status" in request.data:
            if request.data.get("status") not in dict(Estimate.STATUS):
                return Response({"detail": "Некорректный статус сметы"},
                                status=status.HTTP_400_BAD_REQUEST)
            row.status = request.data["status"]
        if isinstance(request.data.get("lines"), list):
            row.lines = request.data["lines"][:500]
        if isinstance(request.data.get("totals"), dict):
            row.totals = request.data["totals"]
        row.version += 1
        row.save()
        return Response(self._serialize(row, request.user))

    @classmethod
    def _serialize(cls, row, user):
        return {
            "id": row.id, "name": row.name, "contact_id": row.contact_id,
            "contact_name": str(row.contact), "deal_id": row.deal_id,
            "project_uuid": row.project.project_uuid if row.project_id else None,
            "owner_id": row.owner_id, "status": row.status, "version": row.version,
            "can_edit": cls._can_edit(user, row),
            "measurement": row.measurement_snapshot, "lines": row.lines,
            "totals": row.totals, "updated_at": row.updated_at.isoformat(),
        }
