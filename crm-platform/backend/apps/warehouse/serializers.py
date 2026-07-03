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
                  "is_active", "category", "category_name", "stock", "margin",
                  "description", "b24_created_by", "b24_modified_by",
                  "b24_created_at", "b24_modified_at", "created_at", "updated_at", "images", "is_bundle",
                  "track_stock"]

    def get_stock(self, obj):
        return obj.stock()

    images = serializers.SerializerMethodField()

    def get_images(self, obj):
        return [{"id": im.id, "url": "/api/products/%d/image/%d/" % (obj.id, im.id)} for im in obj.images.all()]

    is_bundle = serializers.SerializerMethodField()

    def get_is_bundle(self, obj):
        ann = getattr(obj, "_is_bundle", None)
        if ann is not None:
            return bool(ann)
        return obj.components.exists()

    margin = serializers.SerializerMethodField()

    def get_margin(self, obj):
        return float((obj.price or 0) - (obj.cost or 0))

    def to_representation(self, obj):
        data = super().to_representation(obj)
        u = getattr(self.context.get("request"), "user", None)
        if not (u and (getattr(u, "is_superuser", False) or (hasattr(u, "has_perm_code") and u.has_perm_code("product.cost.view")))):
            data.pop("cost", None); data.pop("margin", None)
        return data


class MovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_name", "quantity", "price"]


class StockDocumentSerializer(serializers.ModelSerializer):
    items = MovementSerializer(many=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    deal_title = serializers.CharField(source="deal.title", read_only=True, default=None)

    class Meta:
        model = StockDocument
        fields = ["id", "kind", "kind_display", "number", "warehouse", "comment",
                  "deal", "deal_title", "total", "created_at", "items", "posted", "close_stage"]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        # ручний «Расход» (out) без угоди заборонено — подвійне списання/COGS повз контур.
        # Для порчі/браку/викрасок — kind="writeoff" (обовʼязкова причина в comment).
        if attrs.get("kind") == "out" and not attrs.get("deal"):
            raise serializers.ValidationError(
                "Видатковий документ без угоди заборонено. Для порчі/браку використовуйте «Списання» (writeoff) з причиною.")
        if attrs.get("kind") == "writeoff" and not (attrs.get("comment") or "").strip():
            raise serializers.ValidationError("Для списання вкажіть причину (коментар).")
        # НАБІР не може мати власних рухів (прихід/інвентаризація) — фантомний залишок.
        # Продаж набору списує КОМПОНЕНТИ; повернення набору — прихід компонентів.
        if attrs.get("kind") in ("in", "inv"):
            for it in attrs.get("items") or []:
                prod = it.get("product")
                if prod is not None and prod.components.exists():
                    raise serializers.ValidationError(
                        "«%s» — це набір. Прихід/інвентаризація ведеться по КОМПОНЕНТАХ набору." % prod.name)
        return attrs

    def create(self, validated):
        items = validated.pop("items")
        validated["author"] = self.context["request"].user
        doc = StockDocument.objects.create(**validated)
        for it in items:
            prod = it["product"]
            counted = abs(it["quantity"])
            if doc.kind == "inv":
                # інвентаризація: рух = (факт − обліковий залишок); ЦІНА = собівартість
                # (щоб нестача/надлишок були у грошах, а не по нулях)
                qty = counted - prod.stock(doc.warehouse)
                price = prod.cost or 0
            elif doc.kind == "out":
                qty = -counted          # видаток по угоді
                price = it.get("price", 0)
            elif doc.kind == "writeoff":
                qty = -counted          # списання (порча/брак) — по собівартості
                price = prod.cost or 0
            else:
                qty = counted           # прихід
                price = it.get("price", 0)
            if qty != 0:
                StockMovement.objects.create(document=doc, product=prod,
                                             quantity=qty, price=price)
        if doc.posted:
            from .services import _on_posted
            _on_posted(doc)  # документ народжується проведеним → грошові ефекти одразу
        return doc
