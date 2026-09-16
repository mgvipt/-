"""«Подяка від керівника» (16.09.2026, Олег: «признание можно делать, супер»). Не гроші — видима вдячність за роботу.
Зберігається рядком XPEvent kind="thanks", xp=0 (бали не нараховуються). Дає лише власник / керівник (roles.manage)."""
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import XPEvent


def _can_give(u):
    return bool(u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage")))


class ThanksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = request.GET.get("user") or "me"
        if uid == "me":
            uid = request.user.id
        elif not _can_give(request.user) and str(uid) != str(request.user.id):
            return Response({"detail": "Немає доступу"}, status=403)
        rows = XPEvent.objects.filter(manager_id=uid, kind="thanks").order_by("-created_at")[:30]
        return Response({"items": [{"id": e.id, "date": timezone.localtime(e.created_at).strftime("%d.%m.%Y"),
                                    "text": (e.meta or {}).get("text", ""), "by": (e.meta or {}).get("by", "")} for e in rows],
                         "can_give": _can_give(request.user)})

    def post(self, request):
        if not _can_give(request.user):
            return Response({"detail": "Подяку дає керівник"}, status=403)
        text = str(request.data.get("text") or "").strip()[:300]
        user = get_user_model().objects.filter(id=request.data.get("user"), is_active=True).first()
        if not user or not text:
            return Response({"detail": "Оберіть людину і напишіть, за що дякуєте"}, status=400)
        e = XPEvent.objects.create(manager=user, kind="thanks", xp=0, ref_type="thanks",
                                   ref_id=timezone.now().strftime("%Y%m%d%H%M%S%f")[:40],
                                   meta={"text": text, "by": request.user.get_full_name() or request.user.username})
        return Response({"ok": True, "id": e.id})
