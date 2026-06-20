from rest_framework import serializers
from .models import Warehouse, Product, ProductCategory, StockDocument, StockMovement


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "is_default"]


class ProductCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "parent", "order", "products_count"]

    def get_products_count(self, obj):
        return obj.products.count()


class ProductSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "unit", "price", "cost", "currency",
                  "is_active", "category", "category_name", "stock", "margin"]

    def get_stock(self, obj):
        return obj.stock()

    margin = serializers.SerializerMethodField()

    def get_margin(self, obj):
        return float((obj.price or 0) - (obj.cost or 0))


class MovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_name", "quantity", "price"]


class StockDocumentSerializer(serializers.ModelSerializer):
    items = MovementSerializer(many=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = StockDocument
        fields = ["id", "kind", "kind_display", "number", "warehouse", "comment",
                  "deal", "total", "created_at", "items"]
        read_only_fields = ["created_at"]

    def create(self, validated):
        items = validated.pop("items")
        validated["author"] = self.context["request"].user
        doc = StockDocument.objects.create(**validated)
        for it in items:
            prod = it["product"]
            counted = abs(it["quantity"])
            if doc.kind == "inv":
                # инвентаризация: движение = (факт - текущий остаток), сток становится фактом
                qty = counted - prod.stock(doc.warehouse)
            elif doc.kind == "out":
                qty = -counted          # расход уменьшает остаток
            else:
                qty = counted           # приход увеличивает
            if qty != 0:
                StockMovement.objects.create(document=doc, product=prod,
                                             quantity=qty, price=it.get("price", 0))
        return doc
