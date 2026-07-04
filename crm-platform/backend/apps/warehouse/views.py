from decimal import Decimal
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from apps.common.permissions import HasPermCode
from .models import Warehouse, Product, ProductCategory, StockDocument, StockMovement
from .serializers import WarehouseSerializer, ProductSerializer, StockDocumentSerializer, ProductCategorySerializer


class WarehousePerm(HasPermCode):
    pass


from rest_framework.permissions import BasePermission, SAFE_METHODS


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

    @action(detail=True, methods=["get"], url_path="image/(?P<img_id>[0-9]+)")
    def image(self, request, pk=None, img_id=None):
        """Отдать картинку товара (файл из warehouse_photos/products/)."""
        from django.http import FileResponse, Http404
        from .models import ProductImage
        try:
            im = ProductImage.objects.get(id=img_id, product_id=pk)
            return FileResponse(open(im.file_path, "rb"))
        except (ProductImage.DoesNotExist, FileNotFoundError):
            raise Http404

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

    @action(detail=False, methods=["post"], url_path="import-receipt")
    def import_receipt(self, request):
        """Прихід файлом: CSV (Артикул;Кількість;Ціна) → знайти товар по артикулу/назві → прихід одним документом.
        commit=false → лише прев'ю (нічого не пише). Ненайдені товари — у помилки (прихід для невідомого товару не робимо)."""
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
        })


class InventorySheetView(APIView):
    """Инвентаризационная ведомость за период:
    Початковий залишок (до from) + Надходження − Продано(витрата) = Кінцевий обліковий.
    Факт вносится вручную на фронте, Розбіжність = Факт − Кінцевий.
    Параметры: ?ids=1,2,3 &from=YYYY-MM-DD &to=YYYY-MM-DD (по умолч. текущий месяц)."""

    def get(self, request):
        from datetime import date
        from django.utils import timezone
        ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
        if not ids:
            return Response({"from": "", "to": "", "rows": []})
        now = timezone.now()
        d_from = request.GET.get("from") or now.replace(day=1).date().isoformat()
        d_to = request.GET.get("to") or now.date().isoformat()
        try:
            df = date.fromisoformat(d_from)
            dt = date.fromisoformat(d_to)
        except (ValueError, TypeError):
            return Response({"detail": "Невірний формат дати", "from": d_from, "to": d_to, "rows": []}, status=400)
        agg = (StockMovement.objects.filter(product_id__in=ids, document__posted=True).values("product_id").annotate(
            opening=Coalesce(Sum("quantity", filter=Q(document__created_at__date__lt=df)), Decimal("0")),
            received=Coalesce(Sum("quantity", filter=Q(quantity__gt=0,
                document__created_at__date__gte=df, document__created_at__date__lte=dt)), Decimal("0")),
            sold_neg=Coalesce(Sum("quantity", filter=Q(quantity__lt=0,
                document__created_at__date__gte=df, document__created_at__date__lte=dt)), Decimal("0")),
        ))
        by_id = {a["product_id"]: a for a in agg}
        order = {pid: i for i, pid in enumerate(ids)}
        rows = []
        for p in Product.objects.filter(id__in=ids):
            a = by_id.get(p.id, {})
            opening = a.get("opening") or Decimal("0")
            received = a.get("received") or Decimal("0")
            sold = abs(a.get("sold_neg") or Decimal("0"))
            book = opening + received - sold
            rows.append({"id": p.id, "name": p.name, "unit": p.unit,
                         "opening": float(opening), "received": float(received),
                         "sold": float(sold), "book": float(book)})
        rows.sort(key=lambda x: order.get(x["id"], 9999))
        return Response({"from": d_from, "to": d_to, "rows": rows})
