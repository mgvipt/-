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
    shop_validation_errors = serializers.SerializerMethodField()
    shop_group_variants = serializers.SerializerMethodField()
    shop_sync_history = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "unit", "price", "cost", "cost_pct", "min_price", "currency",
                  "is_active", "category", "category_name", "stock", "margin",
                  "description", "b24_created_by", "b24_modified_by",
                  "b24_created_at", "b24_modified_at", "created_at", "updated_at", "images", "is_bundle",
                  "track_stock", "reserved_qty", "is_drop",
                  "shop_managed", "shop_enabled", "shop_category_path", "shop_status", "shop_group_key", "shop_parent_name",
                  "shop_slug", "shop_short_description", "shop_full_description", "shop_benefits",
                  "shop_effect", "shop_rooms", "shop_beginner", "shop_video_url", "shop_instruction_url",
                  "shop_sort", "shop_badges", "shop_variant_type", "shop_has_board", "shop_is_tinted",
                  "shop_variant_order", "shop_variant_name", "shop_contents", "seo_title", "seo_description",
                  "shop_specs",
                  "seo_h1", "seo_categories", "seo_faqs", "seo_index", "shop_last_sync_at",
                  "shop_sync_error", "shop_remote_url", "shop_validation_errors", "shop_group_variants",
                  "shop_sync_history"]
        read_only_fields = ["shop_managed", "shop_status", "shop_last_sync_at", "shop_sync_error", "shop_remote_url"]

    def get_stock(self, obj):
        return obj.stock()

    images = serializers.SerializerMethodField()

    def get_images(self, obj):
        return [{
            "id": im.id, "url": "/api/products/%d/image/%d/" % (obj.id, im.id),
            "alt_text": im.alt_text, "is_primary": im.is_primary,
            "is_approved": im.is_approved, "variant_key": im.variant_key,
        } for im in obj.images.all()]

    def get_shop_validation_errors(self, obj):
        from .shop_sync import catalog_validation_errors
        return catalog_validation_errors(obj) if obj.shop_managed or obj.category_id == 59 else []

    def get_shop_group_variants(self, obj):
        if not obj.shop_group_key:
            return []
        return list(Product.objects.filter(shop_group_key=obj.shop_group_key).order_by("shop_variant_order", "id").values(
            "id", "sku", "name", "price", "shop_variant_name", "shop_has_board", "shop_is_tinted",
            "shop_variant_order", "shop_status", "shop_enabled",
        ))

    def get_shop_sync_history(self, obj):
        return list(obj.shop_sync_events.order_by("-created_at")[:8].values(
            "event_uuid", "action", "status", "attempts", "last_error", "created_at", "processed_at"
        ))

    reserved_qty = serializers.SerializerMethodField()

    def get_reserved_qty(self, obj):
        """У резерві під активні сделки (не won/lost). Доступно = залишок − резерв."""
        from django.db.models import Sum
        v = obj.deal_items.filter(reserved=True, deal__stage__is_won=False,
                                  deal__stage__is_lost=False).aggregate(s=Sum("quantity"))["s"]
        return float(v or 0)

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

    def create(self, validated_data):
        product = super().create(validated_data)
        self._queue_shop_change(product)
        return Product.objects.get(pk=product.pk)

    def update(self, instance, validated_data):
        was_managed = instance.shop_managed
        product = super().update(instance, validated_data)
        self._queue_shop_change(product, was_managed=was_managed)
        return Product.objects.get(pk=product.pk)

    def _queue_shop_change(self, product, was_managed=False):
        from .shop_sync import SAMPLE_CATEGORY_ID, prepare_product_for_shop, prepare_regular_product_for_shop, queue_product_sync
        if product.category_id == SAMPLE_CATEGORY_ID:
            prepare_product_for_shop(product)
            product.refresh_from_db()
        elif product.shop_enabled:
            prepare_regular_product_for_shop(product)
            product.refresh_from_db()
        if product.shop_enabled and not product.shop_managed:
            Product.objects.filter(pk=product.pk).update(shop_managed=True)
            product.shop_managed = True
        if product.shop_enabled or product.shop_managed or was_managed:
            queue_product_sync(product, action=None if product.shop_enabled else "hide")


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
    supplier_name = serializers.SerializerMethodField()

    def get_supplier_name(self, obj):
        c = obj.supplier
        if not c:
            return ""
        return (getattr(c, "display_name", "") or " ".join(filter(None, [c.first_name, c.last_name])).strip() or c.nickname or c.phone or ("#%d" % c.id))

    class Meta:
        model = StockDocument
        fields = ["id", "kind", "kind_display", "number", "warehouse", "comment",
                  "deal", "deal_title", "total", "created_at", "items", "posted", "close_stage",
                  "supplier", "supplier_name", "supplier_invoice", "doc_date"]
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
