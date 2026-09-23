"""Internal Product technical facts. No persistence, dosing, or public shop export."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation


def _positive(value):
    try:
        number = Decimal(str(value))
        return number.is_finite() and number > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def technical_data(product):
    raw = (product.shop_specs or {}).get('technical_facts') or {}
    if not isinstance(raw, dict) or raw.get('schema_version') != 1:
        return {'schema_version': 1, 'density': [], 'consumption': [], 'notes': [],
                'technical_review': {'required': False, 'codes': []}}
    data = deepcopy(raw)
    rows = []
    for item in raw.get('density', []):
        if not isinstance(item, dict):
            continue
        item = deepcopy(item)
        scalar = _positive(item.get('value'))
        ranged = (_positive(item.get('min')) and _positive(item.get('max'))
                  and Decimal(str(item['min'])) <= Decimal(str(item['max'])))
        uncertainty = item.get('uncertainty')
        uncertainty_ok = uncertainty is None or (_positive(uncertainty) and scalar
                            and Decimal(str(uncertainty)) < Decimal(str(item['value'])))
        confirmed = (item.get('status') == 'confirmed' and item.get('unit') == 'kg/L'
                     and item.get('state') in ('powder', 'liquid', 'mix', 'cured')
                     and item.get('component') in (None, 'A', 'B', 'A+B')
                     and scalar != ranged and uncertainty_ok)
        if not confirmed:
            item.update(status='unknown', value=None, min=None, max=None, uncertainty=None)
        if item.get('state') not in ('powder', 'liquid', 'mix', 'cured'):
            item['state'] = 'unknown'
        if item.get('component') not in (None, 'A', 'B', 'A+B'):
            item['component'] = None
        if confirmed:
            for key in ('value', 'min', 'max', 'uncertainty'):
                if item.get(key) is not None:
                    item[key] = float(Decimal(str(item[key])))
        # This display payload never authorizes a calculator conversion.
        item['dosing_conversion_allowed'] = False
        rows.append(item)
    data['density'] = rows
    return data


def validate_technical_facts(data):
    """Fail closed before a reviewed import; calculator fields are outside this schema."""
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Unsupported technical schema')
    rows = data.get('density', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Density must be a list of records')
    identifiers = [row.get('id') for row in rows]
    if any(not isinstance(key, str) or not key for key in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError('Each density record requires a unique ID')
    for row in rows:
        if row.get('state') not in ('powder', 'liquid', 'mix', 'cured') or row.get('component') not in (None, 'A', 'B', 'A+B'):
            raise ValueError('Invalid density state/component')
        if row.get('unit') != 'kg/L' or row.get('status') not in ('confirmed', 'unknown'):
            raise ValueError('Invalid density unit/status')
        if not isinstance(row.get('original'), dict) or not isinstance(row.get('source'), dict):
            raise ValueError('Original measurement and source required')
        class Holder:
            shop_specs = {'technical_facts': data}
        normalized = technical_data(Holder())
        if row['status'] == 'confirmed' and not any(x.get('id') == row.get('id') and x['status'] == 'confirmed' for x in normalized['density']):
            raise ValueError('Density must be finite positive with a valid range/uncertainty')
        if row['status'] == 'unknown' and any(row.get(key) is not None for key in ('value', 'min', 'max', 'uncertainty')):
            raise ValueError('Unknown density cannot carry an operational number')
    return data


# Imported here to keep the normalization function independently testable.
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Product
from rest_framework.permissions import BasePermission


class TechnicalStaffRead(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active
                    and user.account_kind == 'staff' and (user.is_superuser or any(
            user.has_perm_code(code) for code in ('warehouse.view', 'warehouse.edit', 'inbox.view'))))


class ProductTechnicalSheet(APIView):
    permission_classes = [TechnicalStaffRead]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        try:
            parts = request.query_params.get('ids', '').split(',')
            ids = list(dict.fromkeys(int(x) for x in parts))
            if not ids or len(ids) > 500 or any(x <= 0 for x in ids):
                raise ValueError
        except (ValueError, TypeError):
            return Response({'detail': 'Оберіть від 1 до 500 товарів.'}, status=400)
        lang = 'ru' if request.query_params.get('lang') == 'ru' else 'uk'
        from apps.content_library.client_materials import product_texts
        products = Product.objects.filter(pk__in=ids).only('id', 'name', 'unit', 'price', 'currency',
            'updated_at', 'shop_specs', 'pack_factor', 'description', 'shop_short_description', 'shop_full_description')
        items = [{'id': p.id, 'name': product_texts(p, lang)['name'], 'unit': p.unit,
                  'price': str(p.price) if _positive(p.price) and (p.shop_specs or {}).get('price_status') != 'quote_required' else None,
                  'price_status': 'available' if _positive(p.price) and (p.shop_specs or {}).get('price_status') != 'quote_required' else 'quote_required', 'currency': p.currency, 'pack_factor': str(p.pack_factor) if p.pack_factor is not None else None, 'updated_at': p.updated_at.isoformat(),
                  'technical': technical_data(p)} for p in products.order_by('name', 'id')]
        response = Response({'items': items, 'missing_ids': sorted(set(ids) - {p['id'] for p in items})})
        response['Cache-Control'] = 'private, no-store'
        return response
