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


class WarehouseViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseWrite]
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer


class ProductCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseWrite]
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    pagination_class = None  # дерево категорий целиком


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseWrite]
    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer
    search_fields = ["name", "sku"]
    filterset_fields = ["is_active", "category"]
    ordering_fields = ["name", "price", "id", "sku", "cost", "stock"]
    ordering = ["name"]

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
    filterset_fields = ["kind", "warehouse", "deal"]


class InventoryAnalyticsView(APIView):
    """Аналитика по складу: стоимость запасов (по закупке/рознице), по категориям, дефицит."""
    permission_classes = [HasPermCode]
    required_perm = "warehouse.view"

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
        agg = (StockMovement.objects.filter(product_id__in=ids).values("product_id").annotate(
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
