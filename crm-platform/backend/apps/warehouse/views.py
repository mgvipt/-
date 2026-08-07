from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from apps.common.permissions import HasPermCode
from .models import Warehouse, Product, ProductCategory, ProductImage, StockDocument, StockMovement
from .serializers import WarehouseSerializer, ProductSerializer, StockDocumentSerializer, ProductCategorySerializer


class WarehousePerm(HasPermCode):
    pass


from rest_framework.permissions import BasePermission, SAFE_METHODS, AllowAny


class WarehouseWrite(BasePermission):
    """Читати — будь-який авторизований (менеджерам потрібен каталог товарів).
    Змінювати склад/товари — лише право warehouse.edit (#13)."""
    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return u.is_superuser or u.has_perm_code("warehouse.edit")


class RealizationManage(BasePermission):
    """Проведення/скасування реалізації — відповідальний за склад (warehouse.edit) або бухгалтер (finance.manage). Менеджерам — ні."""
    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return False
        return bool(u.is_superuser or u.has_perm_code("warehouse.edit") or u.has_perm_code("finance.manage"))


class WarehouseViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseWrite]
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer


class ProductCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseWrite]
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    pagination_class = None  # дерево категорий целиком

    def destroy(self, request, *args, **kwargs):
        """Удалить папку + ВСЕ подпапки + товары в них.
        Товары с движениями — скрываются (история цела), без движений — удаляются навсегда.
        ?dry=1 → только посчитать (для подтверждения в UI)."""
        from rest_framework.response import Response as _R
        root = self.get_object()
        cats = [root]
        i = 0
        while i < len(cats):  # собрать поддерево
            cats.extend(ProductCategory.objects.filter(parent=cats[i]))
            i += 1
        cat_ids = [c.id for c in cats]
        prods = Product.objects.filter(category_id__in=cat_ids)
        with_mov = prods.filter(movements__isnull=False).distinct()
        without_mov = prods.exclude(id__in=with_mov.values_list("id", flat=True))
        if request.query_params.get("dry"):
            return _R({"categories": len(cats), "products_delete": without_mov.count(),
                       "products_hide": with_mov.count()})
        hid = with_mov.update(is_active=False, category=None)  # скрыть + отвязать
        deleted = without_mov.count()
        for p in without_mov:
            try:
                p.delete()
            except Exception:
                p.is_active = False; p.category = None; p.save(update_fields=["is_active", "category"])
                hid += 1; deleted -= 1
        # запомнить bitrix_id: следующая синхронизация с Б24 НЕ пересоздаст удалённое
        bx_ids = [c.bitrix_id for c in cats if c.bitrix_id]
        if bx_ids:
            try:
                from apps.integrations.models import IntegrationSettings
                st, _ = IntegrationSettings.objects.get_or_create(
                    provider="b24_excluded", defaults={"config": {"sections": []}, "is_active": True})
                st.config["sections"] = sorted(set((st.config.get("sections") or []) + bx_ids))
                st.save(update_fields=["config"])
            except Exception:
                pass
        n_cats = len(cats)
        for c in reversed(cats):  # сначала листья
            c.delete()
        return _R({"ok": True, "categories": n_cats, "products_deleted": deleted, "products_hidden": hid})


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseWrite]
    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer
    search_fields = ["name", "sku"]
    filterset_fields = ["is_active", "category"]
    ordering_fields = ["name", "price", "id", "sku", "cost", "stock"]
    ordering = ["name", "id"]  # id — запасной ключ: 623 тёзки не дублируются при листании

    def get_queryset(self):
        from django.db.models import Exists, OuterRef
        from .models import ProductComponent
        qs = super().get_queryset().annotate(
            _is_bundle=Exists(ProductComponent.objects.filter(bundle=OuterRef("pk"))))
        in_stock = self.request.query_params.get("in_stock")
        if in_stock in ("0", "1"):
            from django.db.models import Sum, Q
            qs = qs.annotate(_stock=Sum("movements__quantity",
                                        filter=Q(movements__document__posted=True)))
            if in_stock == "1":
                qs = qs.filter(_stock__gt=0)
            else:
                qs = qs.filter(Q(_stock__lte=0) | Q(_stock__isnull=True))
        return qs

    @action(detail=False, methods=["get"], url_path="shop-dashboard")
    def shop_dashboard(self, request):
        """Єдиний read-only огляд каталогу сайту для CRM-адмінки."""
        from django.utils import timezone
        from .models import ShopSyncEvent
        from .shop_sync import catalog_validation_errors, effective_category_path

        products = list(
            Product.objects.filter(shop_enabled=True)
            .select_related("category")
            .prefetch_related("images")
            .order_by("shop_parent_name", "shop_group_key", "shop_variant_order", "id")
        )
        grouped = {}
        product_errors = {}
        missing_photo = 0

        for product in products:
            errors = catalog_validation_errors(product)
            product_errors[product.id] = errors
            approved = [image for image in product.images.all() if image.is_approved]
            if not approved:
                missing_photo += 1
            image = next((image for image in approved if image.is_primary), approved[0] if approved else None)
            key = product.shop_group_key or "product-%s" % product.id
            group = grouped.setdefault(key, {
                "key": key,
                "name": product.shop_parent_name or product.name,
                "slug": product.shop_slug,
                "remote_url": product.shop_remote_url,
                "category_path": effective_category_path(product),
                "updated_at": product.updated_at,
                "variants": [],
            })
            if product.shop_remote_url:
                group["remote_url"] = product.shop_remote_url
            if product.updated_at and (not group["updated_at"] or product.updated_at > group["updated_at"]):
                group["updated_at"] = product.updated_at
            group["variants"].append({
                "id": product.id,
                "sku": product.sku,
                "name": product.name,
                "price": str(product.price),
                "variant_order": product.shop_variant_order,
                "variant_name": product.shop_variant_name,
                "variant_type": product.shop_variant_type,
                "enabled": product.shop_enabled,
                "status": product.shop_status,
                "approved_photo": bool(approved),
                "image_url": "/api/products/%s/image/%s/" % (product.id, image.id) if image else "",
                "errors": errors,
            })

        groups = []
        published_groups = 0
        for group in grouped.values():
            variants = sorted(group["variants"], key=lambda row: (row["variant_order"] or 99, row["id"]))
            errors = []
            for variant in variants:
                for error in variant["errors"]:
                    if error not in errors:
                        errors.append(error)
            expected_variants = 4 if any(variant["variant_type"] == "sample" for variant in variants) else 1
            if len(variants) != expected_variants:
                errors.insert(0, "У групі має бути %s комплектацій, зараз %s" % (expected_variants, len(variants)))
            statuses = {variant["status"] for variant in variants}
            enabled_count = sum(1 for variant in variants if variant["enabled"])
            if "error" in statuses:
                status = "error"
            elif len(variants) == expected_variants and statuses == {"published"}:
                status = "published"
                published_groups += 1
            elif enabled_count and not errors:
                status = "ready"
            else:
                status = "draft"
            groups.append({
                **{key: value for key, value in group.items() if key != "variants"},
                "status": status,
                "variants_count": len(variants),
                "expected_variants": expected_variants,
                "enabled_count": enabled_count,
                "approved_photos": sum(1 for variant in variants if variant["approved_photo"]),
                "errors": errors,
                "variants": variants,
                "updated_at": group["updated_at"].isoformat() if group["updated_at"] else None,
            })

        status_order = {"error": 0, "draft": 1, "ready": 2, "published": 3}
        groups.sort(key=lambda group: (status_order[group["status"]], group["name"].lower()))
        pending_events = ShopSyncEvent.objects.filter(status__in=["pending", "processing"]).count()
        failed_events = ShopSyncEvent.objects.filter(status="failed").count()
        return Response({
            "summary": {
                "products": len(products),
                "groups": len(groups),
                "published_groups": published_groups,
                "draft_groups": len(groups) - published_groups,
                "enabled_products": sum(1 for product in products if product.shop_enabled),
                "missing_photo": missing_photo,
                "problem_products": sum(1 for errors in product_errors.values() if errors),
                "pending_events": pending_events,
                "failed_events": failed_events,
            },
            "groups": groups,
            "generated_at": timezone.now().isoformat(),
        })

    def destroy(self, request, *args, **kwargs):
        from rest_framework.response import Response as _R
        p = self.get_object()
        if StockMovement.objects.filter(product=p).exists():
            # товар має рухи → не видаляємо назавжди (історія), а ховаємо
            p.is_active = False
            p.save(update_fields=["is_active"])
            return _R({"hidden": True, "detail": "Товар має рухи на складі — приховано (історія збережена)."})
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def export(self, request):
        import csv
        import io as _io
        from django.http import HttpResponse
        qs = self.filter_queryset(self.get_queryset()).select_related("category")
        buf = _io.StringIO()
        buf.write("\ufeff")  # BOM щоб Excel правильно показав кирилицю
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Назва", "Артикул", "Категорія", "Од", "Ціна", "Собівартість", "Валюта"])
        for p in qs:
            w.writerow([p.name, p.sku, (p.category.name if p.category_id else ""), p.unit,
                        str(p.price), str(p.cost), p.currency])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = "attachment; filename=nomenclatura.csv"
        return resp

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        """Імпорт номенклатури з CSV (колонки: Назва;Артикул;Категорія;Од;Ціна;Собівартість;Валюта).
        Міняє ТІЛЬКИ картку товару (залишок НЕ чіпає). commit=false → лише прев'ю (нічого не пише)."""
        import csv
        import io as _io
        from apps.warehouse.models import ProductCategory
        raw = request.data.get("data") or ""
        commit = bool(request.data.get("commit"))
        if not str(raw).strip():
            return Response({"detail": "Порожній файл"}, status=400)
        delim = ";" if raw.count(";") >= raw.count(",") else ","
        rows = list(csv.reader(_io.StringIO(raw), delimiter=delim))
        start = 0
        if rows:
            hdr = [str(c).strip().lower() for c in rows[0]]
            if any(h in ("назва", "название", "name", "товар", "артикул", "sku") for h in hdr):
                start = 1

        def _num(x):
            try:
                return float(str(x).replace(" ", "").replace("\u00a0", "").replace(",", "."))
            except (TypeError, ValueError):
                return None
        created = updated = errors = 0
        err_samples = []
        for i in range(start, len(rows)):
            r = rows[i]
            if not any((str(c) or "").strip() for c in r):
                continue
            name = (r[0].strip() if len(r) > 0 else "")
            sku = (r[1].strip() if len(r) > 1 else "")
            catname = (r[2].strip() if len(r) > 2 else "")
            unit = (r[3].strip() if len(r) > 3 and r[3].strip() else "шт")
            price = _num(r[4]) if len(r) > 4 and str(r[4]).strip() else 0
            cost = _num(r[5]) if len(r) > 5 and str(r[5]).strip() else 0
            currency = (r[6].strip() if len(r) > 6 and r[6].strip() else "UAH")
            if not (name or sku):
                errors += 1
                if len(err_samples) < 5:
                    err_samples.append("рядок %d: нема назви й артикула" % (i + 1))
                continue
            if price is None or cost is None:
                errors += 1
                if len(err_samples) < 5:
                    err_samples.append("рядок %d: ціна/собівартість не число" % (i + 1))
                continue
            existing = Product.objects.filter(sku=sku).first() if sku else None
            if not existing and name:
                existing = Product.objects.filter(name__iexact=name.strip()).first()
            if existing:
                updated += 1
                if commit:
                    cat = existing.category
                    if catname:
                        cat = ProductCategory.objects.filter(name=catname).first() or ProductCategory.objects.create(name=catname)
                    if name:
                        existing.name = name
                    if sku:
                        existing.sku = sku
                    existing.unit = unit
                    existing.price = price
                    existing.cost = cost
                    existing.currency = currency
                    existing.is_active = True
                    if cat:
                        existing.category = cat
                    existing.save()
            else:
                created += 1
                if commit:
                    cat = None
                    if catname:
                        cat = ProductCategory.objects.filter(name=catname).first() or ProductCategory.objects.create(name=catname)
                    Product.objects.create(name=(name or sku), sku=sku, unit=unit, price=price, cost=cost, currency=currency, category=cat)
        return Response({"created": created, "updated": updated, "errors": errors, "err_samples": err_samples, "committed": commit})

    @action(detail=False, methods=["post"], url_path="bulk-unit")
    def bulk_unit(self, request):
        """Масово змінити одиницю виміру: {ids: [...], unit: "кг"}. Право warehouse.edit."""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("warehouse.edit")):
            return Response({"detail": "Потрібне право «Редагувати склад»"}, status=403)
        ids = request.data.get("ids") or []
        unit = (request.data.get("unit") or "").strip()[:16]
        if not ids or not unit:
            return Response({"detail": "Вкажіть товари та одиницю"}, status=400)
        n = Product.objects.filter(id__in=ids).update(unit=unit)
        return Response({"ok": True, "updated": n, "unit": unit})

    @action(detail=True, methods=["get", "post"])
    def components(self, request, pk=None):
        """Склад набору. GET → список компонентів + скільки наборів можна зібрати.
        POST {components: [{component: id, quantity}]} → замінити склад (авто-cost)."""
        from decimal import Decimal
        p = self.get_object()
        if request.method == "POST":
            if not (request.user.is_superuser or request.user.has_perm_code("warehouse.edit")):
                return Response({"detail": "Потрібне право «Редагувати склад»"}, status=403)
            from .services import set_bundle_components
            _, err = set_bundle_components(p, request.data.get("components") or [])
            if err:
                return Response({"detail": err}, status=400)
        rows = []
        can_build = None
        comp_cost = Decimal("0")
        for row in p.components.select_related("component"):
            st = row.component.stock()
            rows.append({"id": row.id, "component": row.component_id, "name": row.component.name,
                         "sku": row.component.sku, "unit": row.component.unit,
                         "quantity": float(row.quantity),
                         "cost": float(row.component.cost or 0),
                         "price": float(row.component.price or 0),
                         "track_stock": row.component.track_stock,
                         "stock": float(st)})
            comp_cost += (row.component.cost or Decimal("0")) * row.quantity
            if row.quantity > 0 and row.component.track_stock:
                n = int(Decimal(st) / row.quantity)
                can_build = n if can_build is None else min(can_build, n)
        from .services import bundle_assembly_fee
        fee = bundle_assembly_fee() if rows else Decimal("0")
        return Response({"components": rows, "cost": float(p.cost or 0),
                         "components_cost": float(comp_cost), "assembly_fee": float(fee),
                         "can_build": (can_build if rows else None)})

    @action(detail=True, methods=["get"], url_path="image/(?P<img_id>[0-9]+)", permission_classes=[AllowAny])
    def image(self, request, pk=None, img_id=None):
        """Отдать картинку товара (файл из warehouse_photos/products/)."""
        from django.http import FileResponse, Http404
        from .models import ProductImage
        try:
            im = ProductImage.objects.get(id=img_id, product_id=pk)
            return FileResponse(open(im.file_path, "rb"))
        except (ProductImage.DoesNotExist, FileNotFoundError):
            raise Http404

    @action(detail=True, methods=["get"], url_path="shop-validate")
    def shop_validate(self, request, pk=None):
        """Чекліст готовності товару до публікації."""
        from .shop_sync import catalog_validation_errors, prepare_product_for_shop
        product = prepare_product_for_shop(self.get_object())
        errors = catalog_validation_errors(product)
        return Response({"ok": not errors, "status": product.shop_status, "errors": errors})

    @action(detail=True, methods=["post"], url_path="shop-sync")
    def shop_sync(self, request, pk=None):
        """Поставити одну актуальну версію картки в надійну чергу магазину."""
        from .shop_sync import queue_product_sync
        product = self.get_object()
        if not product.shop_enabled:
            return Response({"detail": "Спочатку увімкніть «Показувати в інтернет-магазині»."}, status=400)
        event = queue_product_sync(product)
        product.refresh_from_db()
        return Response({"queued": True, "event_uuid": event.event_uuid,
                         "status": product.shop_status,
                         "errors": event.payload.get("product", {}).get("validation_errors", [])})

    @action(detail=True, methods=["post"], url_path="shop-images")
    def upload_shop_image(self, request, pk=None):
        """Завантажити фото; воно не піде на сайт, поки менеджер його не затвердить."""
        import mimetypes
        import os
        import uuid
        from django.conf import settings
        from .shop_sync import queue_product_sync
        product = self.get_object()
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "Оберіть файл."}, status=400)
        allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
        content_type = (uploaded.content_type or mimetypes.guess_type(uploaded.name)[0] or "").lower()
        if content_type not in allowed:
            return Response({"detail": "Дозволені JPG, PNG або WEBP."}, status=400)
        if uploaded.size > 10 * 1024 * 1024:
            return Response({"detail": "Фото завелике. Максимум 10 МБ."}, status=400)
        root = getattr(settings, "WAREHOUSE_PHOTOS_DIR", "/app/warehouse_photos")
        folder = os.path.join(root, "products")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"shop_{product.id}_{uuid.uuid4().hex}{allowed[content_type]}")
        with open(path, "wb") as target:
            for chunk in uploaded.chunks():
                target.write(chunk)
        image = ProductImage.objects.create(
            product=product, file_path=path, order=product.images.count(),
            alt_text=(request.data.get("alt_text") or product.shop_parent_name or product.name)[:255],
            variant_key=(request.data.get("variant_key") or "")[:40],
        )
        queue_product_sync(product)
        return Response({"id": image.id, "url": f"/api/products/{product.id}/image/{image.id}/",
                         "is_approved": False, "is_primary": False}, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path="shop-images/(?P<img_id>[0-9]+)")
    def manage_shop_image(self, request, pk=None, img_id=None):
        """Затвердити/обрати головне/описати або видалити фото конкретного товару."""
        import os
        from .shop_sync import queue_product_sync
        product = self.get_object()
        try:
            image = ProductImage.objects.get(pk=img_id, product=product)
        except ProductImage.DoesNotExist:
            return Response({"detail": "Фото не знайдено."}, status=404)
        if request.method == "DELETE":
            path = image.file_path
            image.delete()
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            queue_product_sync(product)
            return Response(status=204)
        fields = []
        for field in ("alt_text", "variant_key", "is_approved", "is_primary"):
            if field in request.data:
                value = request.data[field]
                if field in ("is_approved", "is_primary"):
                    value = str(value).lower() in ("1", "true", "yes", "on")
                setattr(image, field, value)
                fields.append(field)
        if image.is_primary:
            ProductImage.objects.filter(product=product).exclude(pk=image.pk).update(is_primary=False)
        if fields:
            image.save(update_fields=fields)
        queue_product_sync(product)
        return Response({"id": image.id, "alt_text": image.alt_text,
                         "variant_key": image.variant_key, "is_approved": image.is_approved,
                         "is_primary": image.is_primary})

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
    permission_classes = [WarehouseWrite]
    queryset = StockDocument.objects.prefetch_related("items").select_related("warehouse", "deal")
    serializer_class = StockDocumentSerializer
    filterset_fields = ["kind", "warehouse", "deal", "posted"]

    # право на перегляд документів за типом (вкладки Складського обліку)
    KIND_PERM = {"out": "warehouse.tab.realizations", "in": "warehouse.tab.receipts",
                 "inv": "warehouse.tab.inventory", "writeoff": "warehouse.tab.inventory"}

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        # документи конкретної сделки (блок «Сума» у картці) — доступні відповідальному як і раніше
        if u.is_superuser or "deal" in self.request.query_params:
            return qs
        deny = [k for k, p in self.KIND_PERM.items() if not u.has_perm_code(p)]
        return qs.exclude(kind__in=deny) if deny else qs

    def create(self, request, *args, **kwargs):
        # створювати документ конкретного типу може лише той, у кого право на цей тип
        # (напр. «Прихід» in → warehouse.tab.receipts). Відділ продажів такого права не має.
        u = request.user
        kind = request.data.get("kind", "out")
        perm = self.KIND_PERM.get(kind)
        if perm and not (u.is_superuser or u.has_perm_code(perm)):
            return Response({"detail": "Немає права створювати документ цього типу."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="post", permission_classes=[RealizationManage])
    def post_doc(self, request, pk=None):
        """Провести документ (рухи рахуються у залишок; для реалізації — бронь COGS)."""
        from .services import post_document
        doc = self.get_object()
        changed = post_document(doc)
        return Response({"ok": True, "changed": changed, "posted": doc.posted})

    @action(detail=True, methods=["post"], url_path="unpost", permission_classes=[RealizationManage])
    def unpost_doc(self, request, pk=None):
        """Скасувати проведення (залишок повертається; COGS сторнується)."""
        from .services import unpost_document
        doc = self.get_object()
        changed = unpost_document(doc)
        return Response({"ok": True, "changed": changed, "posted": doc.posted})

    @action(detail=True, methods=["post"], url_path="void")
    def void_doc(self, request, pk=None):
        """Сторно інвентаризації (kind=inv): залишок відкочується, документ ЛИШАЄТЬСЯ в історії як «скасовано».
        Право — warehouse.inventory.void (окремий відповідальний), не звичайний менеджер."""
        u = request.user
        doc = self.get_object()
        if doc.kind != "inv":
            return Response({"detail": "Сторно доступне лише для інвентаризації."}, status=status.HTTP_400_BAD_REQUEST)
        if not (u.is_superuser or u.has_perm_code("warehouse.inventory.void")):
            return Response({"detail": "Немає права скасовувати інвентаризацію."}, status=status.HTTP_403_FORBIDDEN)
        from .services import unpost_document
        changed = unpost_document(doc)
        return Response({"ok": True, "changed": changed, "posted": doc.posted})

    def destroy(self, request, *args, **kwargs):
        """Інвентаризацію НЕ видаляємо фізично (аудит-слід) — тільки сторно через /void/.
        Інші типи документів — стандартна поведінка ModelViewSet."""
        doc = self.get_object()
        if doc.kind == "inv":
            return Response({"detail": "Інвентаризацію не можна видаляти. Скористайтесь «Скасувати» (сторно) — запис лишиться в історії."},
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="import-receipt")
    def import_receipt(self, request):
        """Прихід файлом: CSV (Артикул;Кількість;Ціна) → знайти товар по артикулу/назві → прихід одним документом.
        commit=false → лише прев'ю (нічого не пише). Ненайдені товари — у помилки (прихід для невідомого товару не робимо)."""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("warehouse.tab.receipts")):
            return Response({"detail": "Немає права на прихід."}, status=status.HTTP_403_FORBIDDEN)
        import csv
        import io as _io
        from apps.warehouse.models import Product, Warehouse, StockMovement, StockDocument
        raw = request.data.get("data") or ""
        commit = bool(request.data.get("commit"))
        if not str(raw).strip():
            return Response({"detail": "Порожній файл"}, status=400)
        delim = ";" if raw.count(";") >= raw.count(",") else ","
        rows = list(csv.reader(_io.StringIO(raw), delimiter=delim))
        start = 0
        if rows:
            hdr = [str(c).strip().lower() for c in rows[0]]
            if any(h in ("артикул", "sku", "назва", "название", "товар", "кількість", "количество", "qty", "ціна", "цена") for h in hdr):
                start = 1

        def _num(x):
            try:
                return float(str(x).replace(" ", "").replace("\u00a0", "").replace(",", "."))
            except (TypeError, ValueError):
                return None
        items = []
        errors = 0
        err_samples = []
        total_qty = 0.0
        total_sum = 0.0
        for i in range(start, len(rows)):
            r = rows[i]
            if not any((str(c) or "").strip() for c in r):
                continue
            key = (r[0].strip() if len(r) > 0 else "")
            qty = _num(r[1]) if len(r) > 1 else None
            price = _num(r[2]) if len(r) > 2 and str(r[2]).strip() else None
            if not key or qty is None or qty <= 0:
                errors += 1
                if len(err_samples) < 6:
                    err_samples.append("рядок %d: нема артикула/кількості" % (i + 1))
                continue
            p = Product.objects.filter(sku=key).first() or Product.objects.filter(name__iexact=key).first()
            if not p:
                errors += 1
                if len(err_samples) < 6:
                    err_samples.append("рядок %d: товар не знайдено «%s»" % (i + 1, key[:30]))
                continue
            if price is None:
                price = float(p.cost or 0)
            items.append((p, qty, price))
            total_qty += qty
            total_sum += qty * price
        res = {"positions": len(items), "total_qty": round(total_qty, 2), "total_sum": round(total_sum, 2),
               "errors": errors, "err_samples": err_samples, "committed": False}
        if commit and items:
            wh = Warehouse.objects.filter(id=request.data.get("warehouse")).first() or Warehouse.objects.first()
            doc = StockDocument.objects.create(warehouse=wh, kind="in")
            for (p, qty, price) in items:
                StockMovement.objects.create(document=doc, product=p, quantity=qty, price=price)
            from .services import _on_posted
            _on_posted(doc)  # перерахунок середньозваженої собівартості
            res["committed"] = True
            res["doc_id"] = doc.id
        return Response(res)

    @action(detail=False, methods=["post"], url_path="import-inventory")
    def import_inventory(self, request):
        """Імпорт інвентаризації: файл (xlsx/csv), вставлений текст АБО фото (ІІ розпізнає рукописний факт).
        Прев'ю: commit=false + джерело (data / xlsx_b64 / images) → {matched, changed, not_found, preview}.
        Провести: commit=true + items=[{product, fact}] (відредагований список) → документ інвентаризації.
        Право — warehouse.tab.inventory."""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("warehouse.tab.inventory")):
            return Response({"detail": "Немає права на інвентаризацію."}, status=status.HTTP_403_FORBIDDEN)

        commit = bool(request.data.get("commit"))

        # ── ПРОВЕСТИ за відредагованим списком позицій ──
        if commit and request.data.get("items"):
            from datetime import date as _date
            pairs = []
            for it in (request.data.get("items") or []):
                try:
                    pid = int(it.get("product")); fact = float(it.get("fact"))
                except (TypeError, ValueError, AttributeError):
                    continue
                p = Product.objects.filter(id=pid).first()
                if p:
                    pairs.append((p, fact))
            if not pairs:
                return Response({"detail": "Немає позицій для проведення."}, status=400)
            dd = request.data.get("doc_date"); doc_date = None
            if dd:
                try:
                    doc_date = _date.fromisoformat(str(dd)[:10])
                except (ValueError, TypeError):
                    doc_date = None
            wh = Warehouse.objects.filter(id=request.data.get("warehouse")).first() or Warehouse.objects.first()
            doc = StockDocument.objects.create(warehouse=wh, kind="inv", doc_date=doc_date,
                                               comment=(request.data.get("comment") or "Інвентаризація (імпорт)"))
            n = 0
            for (p, fact) in pairs:
                qty = fact - float(p.stock())
                if qty != 0:
                    StockMovement.objects.create(document=doc, product=p, quantity=qty, price=(p.cost or 0)); n += 1
            from .services import _on_posted
            _on_posted(doc)
            return Response({"committed": True, "doc_id": doc.id, "changed": n})

        # ── ПРЕВ'Ю: зібрати entries [{sku, name, fact}] з джерела ──
        entries = []
        images = request.data.get("images") or []
        xlsx_b64 = request.data.get("xlsx_b64") or ""
        raw = request.data.get("data") or ""
        if images:
            from apps.crm.ai import claude_vision
            imgs = []
            for u_img in images[:24]:
                sv = str(u_img)
                if sv.startswith("data:") and "," in sv:
                    head, b64 = sv.split(",", 1)
                    mt = head[5:].split(";")[0] or "image/jpeg"
                else:
                    mt, b64 = "image/jpeg", sv
                if b64:
                    imgs.append((mt, b64))
            if not imgs:
                return Response({"detail": "Порожні зображення."}, status=400)
            system = ("Ти розпізнаєш РУКОПИСНІ інвентаризаційні відомості складу. На фото таблиця з колонками: "
                      "№, Артикул (може бути), Товар (назва), Од., Облік, Факт (вписаний ВІД РУКИ), Примітка. "
                      "Витягни КОЖЕН рядок, де у колонці «Факт» є рукописне число. Поверни артикул (якщо видно), "
                      "назву товару та число «Факт» (може бути дробовим, кг). Рядки без рукописного факту — пропусти. "
                      "Відповідь — СТРОГО JSON-масив: [{\"sku\": \"...\", \"name\": \"...\", \"fact\": <число>}]. Без пояснень і тексту поза JSON.")
            data = []
            for _bi in range(0, len(imgs), 5):      # батчі по 5 фото — щоб не впертись у ліміт токенів відповіді
                batch = imgs[_bi:_bi + 5]
                try:
                    part = claude_vision(batch, "Розпізнай відомість і поверни JSON-масив рядків з рукописним фактом.",
                                         system=system, source="inv_photo")
                except Exception as e:
                    return Response({"detail": "ІІ не зміг обробити фото: %s" % str(e)[:150]}, status=502)
                if isinstance(part, dict):
                    part = part.get("rows") or part.get("items") or []
                if isinstance(part, list):
                    data.extend(part)
            for it in (data or []):
                try:
                    entries.append({"sku": str(it.get("sku") or "").strip(),
                                    "name": str(it.get("name") or "").strip(),
                                    "fact": float(it.get("fact"))})
                except (TypeError, ValueError, AttributeError):
                    continue
        else:
            import csv
            import io as _io
            import base64
            rows = []
            if xlsx_b64:
                try:
                    blob = base64.b64decode(str(xlsx_b64).split(",")[-1])
                    import openpyxl
                    wb = openpyxl.load_workbook(_io.BytesIO(blob), read_only=True, data_only=True)
                    for r in wb.active.iter_rows(values_only=True):
                        rows.append(["" if c is None else str(c) for c in r])
                except Exception:
                    return Response({"detail": "Не вдалося прочитати Excel-файл. Перевірте, що це .xlsx."}, status=400)
            elif str(raw).strip():
                delim = ";" if raw.count(";") >= raw.count(",") else ","
                if raw.count("\t") >= raw.count(delim):
                    delim = "\t"
                rows = [list(r) for r in csv.reader(_io.StringIO(raw), delimiter=delim)]
            else:
                return Response({"detail": "Порожній файл або джерело не вказано"}, status=400)
            start = 0
            if rows:
                hdr = [str(c).strip().lower() for c in rows[0]]
                if any(h in ("артикул", "sku", "назва", "название", "товар", "факт", "fact", "кількість", "количество", "qty") for h in hdr):
                    start = 1

            def _num(x):
                try:
                    return float(str(x).replace(" ", "").replace(" ", "").replace(",", "."))
                except (TypeError, ValueError):
                    return None
            for i in range(start, len(rows)):
                r = rows[i]
                if not any((str(c) or "").strip() for c in r):
                    continue
                key = str(r[0]).strip() if len(r) > 0 else ""
                fact = _num(r[1]) if len(r) > 1 else None
                nm = str(r[2]).strip() if len(r) > 2 else ""
                if not key or fact is None:
                    if key or (len(r) > 1 and str(r[1]).strip()):
                        entries.append({"sku": "", "name": "", "fact": None, "_bad": key or "?"})
                    continue
                entries.append({"sku": key, "name": nm or key, "fact": fact})

        # ── МАТЧ entries → preview (розумне зіставлення: артикул точно/нормалізовано + назва точно/нечітко) ──
        import re as _re
        from difflib import SequenceMatcher as _SM

        def _norm(x):
            return _re.sub(r'[\s"«»\'`´\-_.,;:()/\\]+', '', str(x or '').lower())

        _active = list(Product.objects.filter(is_active=True).only("id", "sku", "name", "unit"))
        _by_sku = {}
        _by_sku_n = {}
        _by_name_n = {}
        _norm_names = []  # (product, norm_name) — для нечіткого пошуку
        for pr in _active:
            if pr.sku:
                _by_sku.setdefault(pr.sku, pr)
                _by_sku_n.setdefault(_norm(pr.sku), pr)
            nn = _norm(pr.name)
            if nn:
                _by_name_n.setdefault(nn, pr)
                _norm_names.append((pr, nn))

        def _match(sku, nm):
            if sku:
                if sku in _by_sku:
                    return _by_sku[sku]
                ns = _norm(sku)
                if ns:
                    if ns in _by_sku_n:
                        return _by_sku_n[ns]
                    if ns in _by_name_n:
                        return _by_name_n[ns]
            if nm:
                nn = _norm(nm)
                if not nn:
                    return None
                if nn in _by_name_n:
                    return _by_name_n[nn]
                sm = _SM(); sm.set_seq2(nn)
                best = None; best_r = 0.0
                for (pr, pnn) in _norm_names:
                    sm.set_seq1(pnn)
                    if sm.real_quick_ratio() < 0.86 or sm.quick_ratio() < 0.86:
                        continue
                    r = sm.ratio()
                    if r > best_r:
                        best_r = r; best = pr
                if best is not None and best_r >= 0.86:
                    return best
            return None

        preview = []
        not_found = []
        seen = set()
        for e in entries:
            if e.get("fact") is None:
                bad = e.get("_bad")
                if bad:
                    not_found.append({"key": str(bad)[:60], "reason": "нема артикула/факту"})
                continue
            sku = e.get("sku") or ""
            nm = e.get("name") or ""
            fact = e["fact"]
            p = _match(sku, nm)
            if not p:
                not_found.append({"key": (sku or nm or "?")[:60], "reason": "товар не знайдено"})
                continue
            if p.id in seen:
                continue
            seen.add(p.id)
            book = float(p.stock())
            preview.append({"id": p.id, "sku": p.sku, "name": p.name, "unit": p.unit,
                            "book": round(book, 2), "fact": round(fact, 2), "delta": round(fact - book, 2)})
        changed = sum(1 for x in preview if x["delta"] != 0)
        return Response({"matched": len(preview), "changed": changed, "not_found": not_found,
                         "preview": preview, "committed": False})

class ProductShipmentsView(APIView):
    """Відвантаження (реалізації) конкретного товару за період — щоб з рядка тижневої ведомості
    перейти у сделки, які «поїхали» з цим товаром. Право warehouse.tab.inventory."""
    permission_classes = [HasPermCode]
    required_perm = "warehouse.tab.inventory"

    def get(self, request):
        from datetime import date
        from django.utils import timezone
        pid = request.GET.get("product")
        if not (pid and str(pid).isdigit()):
            return Response({"rows": [], "count": 0})
        now = timezone.now()
        d_from = request.GET.get("from") or now.replace(day=1).date().isoformat()
        d_to = request.GET.get("to") or now.date().isoformat()
        try:
            df = date.fromisoformat(d_from)
            dt = date.fromisoformat(d_to)
        except (ValueError, TypeError):
            return Response({"rows": [], "count": 0}, status=400)
        movs = (StockMovement.objects.filter(
            product_id=int(pid), quantity__lt=0, document__posted=True, document__kind="out",
            document__created_at__date__gte=df, document__created_at__date__lte=dt)
            .select_related("document", "document__deal", "document__deal__contact")
            .order_by("-document__created_at"))
        rows = []
        for m in movs:
            d = m.document
            deal = d.deal
            cname = ""
            if deal and deal.contact_id:
                c = deal.contact
                cname = str(c) or ("%s %s" % (c.first_name or "", c.last_name or "")).strip()
            rows.append({
                "doc_id": d.id, "number": d.number,
                "deal": deal.id if deal else None,
                "deal_title": (getattr(deal, "title", "") if deal else "") or d.comment or "",
                "contact": cname,
                "qty": float(-m.quantity),
                "date": d.created_at.date().isoformat() if d.created_at else "",
            })
        return Response({"rows": rows, "count": len(rows)})


class InventoryAnalyticsView(APIView):
    """Аналитика по складу: стоимость запасов (по закупке/рознице), по категориям, дефицит."""
    permission_classes = [HasPermCode]
    required_perm = "analytics.warehouse"

    def get(self, request):
        prods = (Product.objects.annotate(stk=Coalesce(Sum("movements__quantity", filter=Q(movements__document__posted=True)), Decimal("0")))
                 .select_related("category"))
        total_items = in_stock = out_stock = 0
        val_cost = val_retail = total_qty = Decimal("0")
        by_cat = {}
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        from apps.warehouse.models import StockMovement as _SM
        _dead_days = 90
        _recent = set(_SM.objects.filter(quantity__lt=0, document__created_at__gte=_tz.now() - _td(days=_dead_days)).values_list("product_id", flat=True))
        _rows = []
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
                _rows.append({"id": p.id, "name": p.name, "sku": p.sku, "unit": p.unit,
                              "qty": round(float(s), 2), "frozen": round(float(vc), 2), "dead": p.id not in _recent})
            else:
                out_stock += 1
        cats = sorted(by_cat.items(), key=lambda kv: -kv[1]["retail"])
        # довідково: втрати складу (НЕ каса — гроші пішли при закупівлі)
        from apps.warehouse.models import StockMovement as _SM2
        _loss_wo = float(sum(abs(m.quantity) * (m.price or 0) for m in _SM2.objects.filter(
            document__kind="writeoff", document__posted=True,
            document__created_at__gte=_tz.now() - _td(days=90))))
        _loss_inv = float(sum(abs(m.quantity) * (m.price or 0) for m in _SM2.objects.filter(
            document__kind="inv", document__posted=True, quantity__lt=0,
            document__created_at__gte=_tz.now() - _td(days=90))))
        # інвентаризація за 90 днів: надлишки (+) і нестачі (-) окремо + останні документи (тільки проведені; сторно НЕ рахується)
        _inv_since = _tz.now() - _td(days=90)
        _inv_surplus = float(sum(m.quantity * (m.price or 0) for m in _SM2.objects.filter(
            document__kind="inv", document__posted=True, quantity__gt=0, document__created_at__gte=_inv_since)))
        _inv_surplus_cnt = _SM2.objects.filter(document__kind="inv", document__posted=True, quantity__gt=0, document__created_at__gte=_inv_since).count()
        _inv_shortage_cnt = _SM2.objects.filter(document__kind="inv", document__posted=True, quantity__lt=0, document__created_at__gte=_inv_since).count()
        _inv_docs = []
        for _d in StockDocument.objects.filter(kind="inv", posted=True, created_at__gte=_inv_since).prefetch_related("items").order_by("-created_at")[:12]:
            _sur = sum(float(m.quantity) * float(m.price or 0) for m in _d.items.all() if m.quantity > 0)
            _sho = sum(abs(float(m.quantity)) * float(m.price or 0) for m in _d.items.all() if m.quantity < 0)
            _dt = _d.doc_date or (_d.created_at.date() if _d.created_at else None)
            _inv_docs.append({"id": _d.id, "date": _dt.isoformat() if _dt else "", "comment": _d.comment,
                              "positions": _d.items.count(), "surplus": round(_sur), "shortage": round(_sho)})
        _frozen_total = round(sum(r["frozen"] for r in _rows))
        _frozen_top = sorted(_rows, key=lambda r: -r["frozen"])[:20]
        _dead = [r for r in _rows if r["dead"]]
        _dead_total = round(sum(r["frozen"] for r in _dead))
        _dead_top = sorted(_dead, key=lambda r: -r["frozen"])[:20]
        _cc = getattr(request.user, "is_superuser", False) or (hasattr(request.user, "has_perm_code") and request.user.has_perm_code("product.cost.view"))
        return Response({
            "total_items": total_items, "in_stock": in_stock, "out_stock": out_stock,
            "total_qty": round(float(total_qty), 1),
            "value_cost": round(float(val_cost)) if _cc else None,
            "value_retail": round(float(val_retail)),
            "potential_margin": round(float(val_retail - val_cost)) if _cc else None,
            "by_category": [{"name": k, "items": v["items"], "qty": round(v["qty"], 1),
                             "cost": round(v["cost"]) if _cc else None, "retail": round(v["retail"])}
                            for k, v in cats],
            "frozen_total": _frozen_total if _cc else None,
            "frozen_top": (_frozen_top if _cc else []),
            "dead_count": len(_dead),
            "dead_total": _dead_total if _cc else None,
            "dead_top": (_dead_top if _cc else []),
            "dead_days": _dead_days,
            "losses_writeoff_90d": round(_loss_wo) if _cc else None,
            "losses_inv_90d": round(_loss_inv) if _cc else None,
            "inv_surplus_90d": round(_inv_surplus) if _cc else None,
            "inv_surplus_cnt": _inv_surplus_cnt,
            "inv_shortage_cnt": _inv_shortage_cnt,
            "inv_docs_90d": (_inv_docs if _cc else []),
        })


class InventorySheetView(APIView):
    """Инвентаризационная ведомость за период.

    Режимы:
      • ?ids=1,2,3 — по конкретному списку id (обратная совместимость).
      • без ids — весь склад с фильтром и пагинацией:
          ?category=<id>          — папка и все её подпапки (пусто = все товары)
          ?search=<txt>           — поиск по названию / артикулу
          ?page=<n>&page_size=<n> — пагинация (по умолч. 1 / 50)
          ?all=1                  — все строки без пагинации (для печати)

    Початковий залишок (до from) + Надходження − Продано = Кінцевий обліковий.
    Факт вносится вручную на фронте, Розбіжність = Факт − Кінцевий.
    Параметры дат: ?from=YYYY-MM-DD &to=YYYY-MM-DD (по умолч. текущий месяц)."""

    @staticmethod
    def _descendant_category_ids(root_id):
        """id папки + все вложенные подпапки (рекурсивно)."""
        pairs = list(ProductCategory.objects.values_list("id", "parent_id"))
        children = {}
        for cid, pid in pairs:
            children.setdefault(pid, []).append(cid)
        result, stack = [], [root_id]
        while stack:
            cur = stack.pop()
            result.append(cur)
            stack.extend(children.get(cur, []))
        return result

    def get(self, request):
        from datetime import date
        from django.utils import timezone
        now = timezone.now()
        d_from = request.GET.get("from") or now.replace(day=1).date().isoformat()
        d_to = request.GET.get("to") or now.date().isoformat()
        try:
            df = date.fromisoformat(d_from)
            dt = date.fromisoformat(d_to)
        except (ValueError, TypeError):
            return Response({"detail": "Невірний формат дати", "from": d_from, "to": d_to,
                             "rows": [], "count": 0, "page": 1, "page_size": 50}, status=400)

        raw_ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
        page, page_size = 1, 50

        if raw_ids:
            # Старый режим: строго по переданным id, в их исходном порядке.
            order = {pid: i for i, pid in enumerate(raw_ids)}
            products = sorted(Product.objects.filter(id__in=raw_ids),
                              key=lambda p: order.get(p.id, 9999))
            count = len(products)
        else:
            # Новый режим: весь склад (только физические товары) с фильтром + пагинация.
            qs = Product.objects.filter(is_active=True, track_stock=True)
            cat_id = request.GET.get("category")
            if cat_id == "none":            # «Без категорії» — товари в корені, не привʼязані до папки
                qs = qs.filter(category__isnull=True)
            elif cat_id and str(cat_id).isdigit():
                qs = qs.filter(category_id__in=self._descendant_category_ids(int(cat_id)))
            if request.GET.get("moved") in ("1", "true", "yes"):
                # тільки товари, що ПРОДАВАЛИСЬ/відвантажувались за період (рух зі знаком мінус) — тижнева перевірка
                _moved_ids = (StockMovement.objects.filter(
                    document__posted=True, quantity__lt=0,
                    document__created_at__date__gte=df, document__created_at__date__lte=dt)
                    .values_list("product_id", flat=True).distinct())
                qs = qs.filter(id__in=list(_moved_ids))
            search = (request.GET.get("search") or "").strip()
            if search:
                qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
            qs = qs.order_by("name", "id")
            count = qs.count()
            if request.GET.get("all") in ("1", "true", "yes"):
                products = list(qs)
                page, page_size = 1, count or 1
            else:
                try:
                    page = max(1, int(request.GET.get("page", 1)))
                except (ValueError, TypeError):
                    page = 1
                try:
                    page_size = min(1000, max(1, int(request.GET.get("page_size", 50))))
                except (ValueError, TypeError):
                    page_size = 50
                start = (page - 1) * page_size
                products = list(qs[start:start + page_size])

        ids = [p.id for p in products]
        if not ids:
            return Response({"from": d_from, "to": d_to, "rows": [],
                             "count": count, "page": page, "page_size": page_size})

        agg = (StockMovement.objects.filter(product_id__in=ids, document__posted=True).values("product_id").annotate(
            opening=Coalesce(Sum("quantity", filter=Q(document__created_at__date__lt=df)), Decimal("0")),
            received=Coalesce(Sum("quantity", filter=Q(quantity__gt=0,
                document__created_at__date__gte=df, document__created_at__date__lte=dt)), Decimal("0")),
            sold_neg=Coalesce(Sum("quantity", filter=Q(quantity__lt=0,
                document__created_at__date__gte=df, document__created_at__date__lte=dt)), Decimal("0")),
        ))
        by_id = {a["product_id"]: a for a in agg}
        rows = []
        for p in products:
            a = by_id.get(p.id, {})
            opening = a.get("opening") or Decimal("0")
            received = a.get("received") or Decimal("0")
            sold = abs(a.get("sold_neg") or Decimal("0"))
            book = opening + received - sold
            rows.append({"id": p.id, "name": p.name, "sku": p.sku, "unit": p.unit,
                         "opening": float(opening), "received": float(received),
                         "sold": float(sold), "book": float(book)})
        return Response({"from": d_from, "to": d_to, "rows": rows,
                         "count": count, "page": page, "page_size": page_size})
