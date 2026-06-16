from rest_framework import viewsets
from apps.common.permissions import HasPermCode
from .models import Warehouse, Product, StockDocument
from .serializers import WarehouseSerializer, ProductSerializer, StockDocumentSerializer


class WarehousePerm(HasPermCode):
    pass


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    search_fields = ["name", "sku"]
    filterset_fields = ["is_active"]


class StockDocumentViewSet(viewsets.ModelViewSet):
    queryset = StockDocument.objects.prefetch_related("items").select_related("warehouse", "deal")
    serializer_class = StockDocumentSerializer
    filterset_fields = ["kind", "warehouse", "deal"]
