from rest_framework import viewsets
from apps.common.permissions import HasPermCode
from .models import Warehouse, Product, ProductCategory, StockDocument
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


class StockDocumentViewSet(viewsets.ModelViewSet):
    queryset = StockDocument.objects.prefetch_related("items").select_related("warehouse", "deal")
    serializer_class = StockDocumentSerializer
    filterset_fields = ["kind", "warehouse", "deal"]
