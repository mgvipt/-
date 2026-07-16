from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ShopCatalogImportBatch, ShopCatalogImportRow
from .shop_import import apply_rows, batch_summary, import_workbook, serialize_row, update_import_row


class WarehouseEditPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (
            user.is_superuser or (hasattr(user, "has_perm_code") and user.has_perm_code("warehouse.edit"))
        ))


def serialize_batch(batch, include_rows=False):
    result = {
        "id": batch.id, "source_name": batch.source_name, "source_hash": batch.source_hash,
        "status": batch.status, "summary": batch.summary,
        "created_at": batch.created_at.isoformat(), "updated_at": batch.updated_at.isoformat(),
    }
    if include_rows:
        result["rows"] = [serialize_row(row) for row in batch.rows.select_related("product")]
    return result


class ShopImportBatchListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        batches = ShopCatalogImportBatch.objects.all()[:10]
        return Response([serialize_batch(batch) for batch in batches])


class ShopImportUploadView(APIView):
    permission_classes = [WarehouseEditPermission]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "Выберите файл Excel"}, status=status.HTTP_400_BAD_REQUEST)
        if not uploaded.name.lower().endswith((".xlsx", ".xlsm")):
            return Response({"detail": "Поддерживаются файлы .xlsx и .xlsm"}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded.size > 10 * 1024 * 1024:
            return Response({"detail": "Файл больше 10 МБ"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            batch = import_workbook(uploaded, request.user)
        except (ValueError, KeyError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialize_batch(batch, include_rows=True), status=status.HTTP_201_CREATED)


class ShopImportBatchDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        batch = ShopCatalogImportBatch.objects.get(pk=pk)
        if not batch.summary:
            batch.summary = batch_summary(batch.rows.select_related("product"))
        return Response(serialize_batch(batch, include_rows=True))


class ShopImportRowView(APIView):
    permission_classes = [WarehouseEditPermission]

    def patch(self, request, pk):
        row = ShopCatalogImportRow.objects.select_related("batch", "product").get(pk=pk)
        columns = request.data.get("source_data")
        if not isinstance(columns, dict):
            return Response({"detail": "Передайте исправленные поля source_data"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialize_row(update_import_row(row, columns)))


class ShopImportApplyView(APIView):
    permission_classes = [WarehouseEditPermission]

    def post(self, request, pk):
        if request.data.get("confirm") is not True:
            return Response({"detail": "Требуется явное подтверждение"}, status=status.HTTP_400_BAD_REQUEST)
        row_ids = request.data.get("row_ids")
        if not isinstance(row_ids, list) or not row_ids:
            return Response({"detail": "Выберите хотя бы одну строку"}, status=status.HTTP_400_BAD_REQUEST)
        batch = ShopCatalogImportBatch.objects.get(pk=pk)
        try:
            rows = apply_rows(batch, row_ids)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"applied": len(rows), "batch": serialize_batch(batch, include_rows=True)})
