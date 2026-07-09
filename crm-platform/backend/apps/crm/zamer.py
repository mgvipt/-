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

        # --- 6. Журнал ---
        log_activity("deal", deal.id, LABEL, detail=detail, user=request.user)

        return Response({"ok": True, "deal_id": deal.id, "deal_title": deal.title})
