from decimal import Decimal
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum
from django.db.models.functions import Coalesce
from apps.common.permissions import HasPermCode
from .models import Warehouse, Product, ProductCategory, StockDocument, StockMovement
from .serializers import WarehouseSerializer, ProductSerializer, StockDocumentSerializer, ProductCategorySerializer


class WarehousePerm(HasPermCode):
    pass


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    pagination_class = None  # дерево категорий целиком


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer
    search_fields = ["name", "sku"]
    filterset_fields = ["is_active", "category"]
    ordering_fields = ["name", "price", "id"]
    ordering = ["name"]

    @action(detail=True, methods=["get"])
    def movements(self, request, pk=None):
        """История движений товара (приход/расход/инвентаризация) для карточки."""
        p = self.get_object()
        mv = (StockMovement.objects.filter(product=p)
              .select_related("document", "document__warehouse")
              .order_by("-document__created_at")[:50])
        return Response([{
            "id": m.id, "kind": m.document.kind,
            "kind_display": m.document.get_kind_display(),
            "quantity": float(m.quantity), "price": float(m.price),
            "warehouse": m.document.warehouse.name,
            "date": m.document.created_at,
            "number": m.document.number or m.document_id,
        } for m in mv])


class StockDocumentViewSet(viewsets.ModelViewSet):
    queryset = StockDocument.objects.prefetch_related("items").select_related("warehouse", "deal")
    serializer_class = StockDocumentSerializer
    filterset_fields = ["kind", "warehouse", "deal"]


class InventoryAnalyticsView(APIView):
    """Аналитика по складу: стоимость запасов (по закупке/рознице), по категориям, дефицит."""

    def get(self, request):
        prods = (Product.objects.annotate(stk=Coalesce(Sum("movements__quantity"), Decimal("0")))
                 .select_related("category"))
        total_items = in_stock = out_stock = 0
        val_cost = val_retail = total_qty = Decimal("0")
        by_cat = {}
        for p in prods:
            total_items += 1
            s = p.stk or Decimal("0")
            cost = p.cost or Decimal("0")
            price = p.price or Decimal("0")
            if s > 0:
                in_stock += 1
                total_qty += s
                vc = s * cost
                vr = s * price
                val_cost += vc
                val_retail += vr
                cn = p.category.name if p.category else "Без категорії"
                c = by_cat.setdefault(cn, {"items": 0, "qty": 0.0, "cost": 0.0, "retail": 0.0})
                c["items"] += 1
                c["qty"] += float(s)
                c["cost"] += float(vc)
                c["retail"] += float(vr)
            else:
                out_stock += 1
        cats = sorted(by_cat.items(), key=lambda kv: -kv[1]["retail"])
        return Response({
            "total_items": total_items, "in_stock": in_stock, "out_stock": out_stock,
            "total_qty": round(float(total_qty), 1),
            "value_cost": round(float(val_cost)),
            "value_retail": round(float(val_retail)),
            "potential_margin": round(float(val_retail - val_cost)),
            "by_category": [{"name": k, "items": v["items"], "qty": round(v["qty"], 1),
                             "cost": round(v["cost"]), "retail": round(v["retail"])}
                            for k, v in cats],
        })
