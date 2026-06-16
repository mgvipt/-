from rest_framework import serializers
from .models import Warehouse, Product, StockDocument, StockMovement


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "is_default"]


class ProductSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "unit", "price", "cost", "is_active", "stock"]

    def get_stock(self, obj):
        return obj.stock()


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
            qty = abs(it["quantity"])
            # расход уменьшает остаток
            if doc.kind == "out":
                qty = -qty
            StockMovement.objects.create(document=doc, product=it["product"],
                                         quantity=qty, price=it.get("price", 0))
        return doc
