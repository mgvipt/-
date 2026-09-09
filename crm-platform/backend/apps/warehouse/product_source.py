"""Canonical product facts; read-only integration and reference-only library media."""
import hashlib
import hmac
import os
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product

TEXT_FIELDS = ('description', 'shop_short_description', 'shop_full_description',
               'shop_effect', 'shop_contents')
SPEC_FIELDS = ('packaging', 'finish', 'washable', 'durability', 'application',
               'self_application', 'limitations', 'recommendation', 'search_terms',
               'sample_size', 'tinting', 'consumption_range')


def validate_specs(specs):
    if not isinstance(specs, dict):
        raise serializers.ValidationError('Характеристики мають бути об’єктом.')
    value = specs.get('consumption_range')
    if value in (None, {}):
        return specs
    try:
        lo, hi = Decimal(str(value['min'])), Decimal(str(value['max']))
        valid = lo.is_finite() and hi.is_finite() and 0 < lo <= hi
        valid = valid and value['unit'] in ('кг/м²', 'л/м²', 'шт/м²', 'мл/м²')
    except (KeyError, TypeError, InvalidOperation):
        valid = False
    if not valid:
        raise serializers.ValidationError('Перевірте одиницю та діапазон витрати: 0 < мінімум ≤ максимум.')
    return specs


def media_index():
    from apps.inbox.models import MediaLibraryItem
    index = {}
    for item in MediaLibraryItem.objects.filter(is_active=True, tags__contains='product:').select_related('file', 'preview_file').defer('file__data', 'preview_file__data').order_by('sort', 'id'):
        # Only explicit product associations. A material-family name is not a SKU.
        if re.search(r'(?:rejected|superseded|archive_only)', item.tags, re.I):
            continue
        for pk in re.findall(r'(?:^|\s)product:(\d+)(?=\s|$)', item.tags):
            index.setdefault(int(pk), []).append(item)
    return index


def product_media(request, product, index=None):
    from apps.inbox.views import _library_item_data
    items = (media_index() if index is None else index).get(product.id, [])
    return [_library_item_data(request, item) for item in items]


def product_data(p):
    specs = p.shop_specs or {}
    return {
        'id': p.id, 'name': p.name, 'sku': p.sku, 'unit': p.unit,
        'price': str(p.price), 'currency': p.currency, 'is_active': p.is_active,
        'updated_at': p.updated_at.isoformat(),
        'consumption_per_m2': str(p.consumption_per_m2) if p.consumption_per_m2 is not None else None,
        'consumption_per_m2_unit': p.unit + '/м²',
        **{key: getattr(p, key) for key in TEXT_FIELDS},
        'shop_specs': {key: specs[key] for key in SPEC_FIELDS if key in specs},
        'card_url': 'https://crm.wallcovdec.com.ua/warehouse?product=%d' % p.id,
    }


class CatalogReadPermission(BasePermission):
    def has_permission(self, request, view):
        expected = os.environ.get('CRM_PRODUCT_READ_TOKEN_SHA256', '')
        supplied = request.headers.get('Authorization', '')
        if not expected or not supplied.startswith('Bearer '):
            return False
        digest = hashlib.sha256(supplied[7:].encode()).hexdigest()
        return hmac.compare_digest(expected, digest)


class ProductReadCatalog(APIView):
    authentication_classes = []
    permission_classes = [CatalogReadPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        fields = ('id', 'name', 'sku', 'unit', 'price', 'currency', 'is_active',
                  'updated_at', 'consumption_per_m2', 'shop_specs') + TEXT_FIELDS
        items = [product_data(p) for p in Product.objects.filter(is_active=True).only(*fields).order_by('id')]
        response = Response({'source': 'Wallcov CRM Product', 'schema_version': 1,
                             'checked_at': timezone.now().isoformat(), 'count': len(items), 'items': items})
        response['Cache-Control'] = 'no-store'
        return response


class ProductFacts(APIView):
    """Edit product facts without publishing a site or touching commercial fields."""
    def get_permissions(self):
        from .views import WarehouseWrite
        return [WarehouseWrite()]

    def get(self, request, pk):
        p = get_object_or_404(Product, pk=pk)
        return Response({**product_data(p), 'media': product_media(request, p)})

    @transaction.atomic
    def patch(self, request, pk):
        p = get_object_or_404(Product.objects.select_for_update(), pk=pk)
        if request.data.get('updated_at') != p.updated_at.isoformat():
            return Response({'detail': 'Картку вже змінили. Оновіть її перед збереженням.'}, status=409)
        allowed = set(TEXT_FIELDS) | {'shop_specs', 'updated_at'}
        if set(request.data) - allowed:
            raise serializers.ValidationError('Дозволено змінювати лише характеристики та описи.')
        changes = {}
        for key in TEXT_FIELDS:
            if key in request.data:
                value = request.data[key]
                if not isinstance(value, str) or len(value) > 20000:
                    raise serializers.ValidationError({key: 'Некоректний текст.'})
                changes[key] = value
        if 'shop_specs' in request.data:
            patch = request.data['shop_specs']
            if not isinstance(patch, dict) or set(patch) - set(SPEC_FIELDS):
                raise serializers.ValidationError('Невідомі характеристики.')
            for key, value in patch.items():
                if key != 'consumption_range' and (not isinstance(value, str) or len(value) > 5000):
                    raise serializers.ValidationError({key: 'Некоректний текст.'})
            merged = {**(p.shop_specs or {}), **patch}
            validate_specs(merged)
            changes['shop_specs'] = merged
        changes['updated_at'] = timezone.now()
        # Explicit update avoids site queues and any unrelated model save hooks.
        Product.objects.filter(pk=p.pk).update(**changes)
        p.refresh_from_db()
        return Response({**product_data(p), 'media': product_media(request, p)})
