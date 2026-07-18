import hashlib
import hmac
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ShopSiteMedia, ShopSiteSettings
from .shop_import_views import WarehouseEditPermission


def _secret():
    return os.environ.get("SHOP_WEBHOOK_SECRET", "")


def _signed_request(url, method="GET", payload=None):
    body = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(_secret().encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    request = Request(url, data=body if method != "GET" else None, method=method, headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "X-Wallcov-Timestamp": stamp, "X-Wallcov-Signature": signature,
    })
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def _shop_url(kind="content"):
    default_root = os.environ.get("SHOP_PUBLIC_URL", "https://wallcovdec.com.ua").rstrip("/")
    if kind == "analytics":
        return os.environ.get("SHOP_SITE_ANALYTICS_URL", f"{default_root}/api/crm/site-analytics")
    return os.environ.get("SHOP_SITE_CONTENT_URL", f"{default_root}/api/crm/site-content/home")


def _error_response(exc):
    if isinstance(exc, HTTPError):
        detail = exc.read().decode(errors="replace")[:500]
        return Response({"detail": f"Магазин ответил {exc.code}: {detail}"}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"detail": f"Магазин временно недоступен: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)


class ShopSiteContentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        record = ShopSiteSettings.objects.filter(key="home").first()
        if record:
            return Response({"draft": record.draft, "published": record.published, "updated_at": record.updated_at, "last_published_at": record.last_published_at})
        try:
            content = _signed_request(_shop_url())["content"]
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return _error_response(exc)
        record = ShopSiteSettings.objects.create(key="home", draft=content, published=content, updated_by=request.user)
        return Response({"draft": record.draft, "published": record.published, "updated_at": record.updated_at, "last_published_at": None})

    def patch(self, request):
        if not WarehouseEditPermission().has_permission(request, self):
            return Response({"detail": "Нет права редактировать магазин"}, status=status.HTTP_403_FORBIDDEN)
        content = request.data.get("content")
        if not isinstance(content, dict):
            return Response({"detail": "Настройки страницы должны быть объектом"}, status=status.HTTP_400_BAD_REQUEST)
        if len(json.dumps(content, ensure_ascii=False)) > 300000:
            return Response({"detail": "Слишком большой объём текста"}, status=status.HTTP_400_BAD_REQUEST)
        record, _ = ShopSiteSettings.objects.get_or_create(key="home")
        record.draft, record.updated_by = content, request.user
        record.save(update_fields=["draft", "updated_by", "updated_at"])
        return Response({"draft": record.draft, "updated_at": record.updated_at})


class ShopSitePublishView(APIView):
    permission_classes = [WarehouseEditPermission]

    def post(self, request):
        if request.data.get("confirm") is not True:
            return Response({"detail": "Требуется подтверждение публикации"}, status=status.HTTP_400_BAD_REQUEST)
        record = ShopSiteSettings.objects.filter(key="home").first()
        if not record or not record.draft:
            return Response({"detail": "Сначала сохраните черновик"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = _signed_request(_shop_url(), "POST", {"content": record.draft})
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return _error_response(exc)
        record.published = record.draft
        record.last_published_at = timezone.now()
        record.updated_by = request.user
        record.save(update_fields=["published", "last_published_at", "updated_by", "updated_at"])
        return Response({"detail": "Изменения опубликованы", "site": result, "last_published_at": record.last_published_at})


class ShopSiteMediaView(APIView):
    permission_classes = [WarehouseEditPermission]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded or uploaded.content_type not in ("image/jpeg", "image/png", "image/webp"):
            return Response({"detail": "Выберите JPG, PNG или WebP"}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded.size > 10 * 1024 * 1024:
            return Response({"detail": "Файл больше 10 МБ"}, status=status.HTTP_400_BAD_REQUEST)
        media = ShopSiteMedia.objects.create(file=uploaded, alt=str(request.data.get("alt", ""))[:255], uploaded_by=request.user)
        return Response({"id": media.id, "url": request.build_absolute_uri(media.file.url), "alt": media.alt}, status=status.HTTP_201_CREATED)


class ShopSiteAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            days = min(365, max(1, int(request.query_params.get("days", 30))))
        except ValueError:
            days = 30
        try:
            return Response(_signed_request(f"{_shop_url('analytics')}?{urlencode({'days': days})}"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return _error_response(exc)
