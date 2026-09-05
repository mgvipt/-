"""Cezar model order shared by paginated nomenclature and shop dashboard."""
import re

from django.db.models.expressions import RawSQL
from rest_framework.filters import OrderingFilter

_CODE = re.compile(r"^LPC-(\d+)([A-Z]*)$", re.I)


def catalog_name(product):
    spec = (product.shop_specs or {}).get("cezar") or {}
    match = _CODE.fullmatch(str(spec.get("code", "")))
    if not match:
        return (product.shop_parent_name or product.name).lower()
    return "плінтус cezar %06d:%s:%06d" % (
        int(match[1]), match[2].upper(), int(spec.get("length") or 0))


class ProductCatalogOrdering(OrderingFilter):
    """Order in PostgreSQL before pagination; explicit column sorting still wins."""
    def filter_queryset(self, request, queryset, view):
        requested = request.query_params.get(self.ordering_param)
        if requested:
            fields = self.remove_invalid_fields(queryset, [x.strip() for x in requested.split(",")], view, request)
            if fields:
                return queryset.order_by(*fields, *([] if any(x.lstrip('-') == 'id' for x in fields) else ['id']))
        # Only static SQL: code and length are read from the canonical product JSON.
        # Other products retain the original name ordering and no records are changed.
        key = RawSQL("""CASE
            WHEN shop_specs->'cezar'->>'code' ~* '^LPC-[0-9]+[A-Z]*$'
            THEN 'Плінтус Cezar ' ||
                lpad(substring(shop_specs->'cezar'->>'code' from '[0-9]+'), 6, '0') || ':' ||
                regexp_replace(upper(shop_specs->'cezar'->>'code'), '^LPC-[0-9]+', '') || ':' ||
                lpad(coalesce(shop_specs->'cezar'->>'length', '0'), 6, '0')
            ELSE warehouse_product.name END""", [])
        return queryset.annotate(_catalog_order=key).order_by('_catalog_order', 'id')
