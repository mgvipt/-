"""API бейджа «звідки клієнт» і списку рекламних фраз (14.09.2026, meta-attr). Лише читання,
крім PUT фраз (тільки суперюзер)."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services

_VIEW_CODES = ("lead.view", "deal.view", "contact.view", "conversation.view", "conversation.view.all")


def _staff_ok(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    has = getattr(user, "has_perm_code", None)
    return bool(has and any(has(code) for code in _VIEW_CODES))


class ContactAttrView(APIView):
    def get(self, request, pk):
        if not _staff_ok(request.user):
            return Response({"detail": "Немає доступу"}, status=status.HTTP_403_FORBIDDEN)
        from apps.crm.models import Contact
        if not Contact.objects.filter(pk=pk).exists():
            return Response({"detail": "Не знайдено"}, status=status.HTTP_404_NOT_FOUND)
        return Response(services.summarize(contact_id=pk))


class ConversationAttrView(APIView):
    def get(self, request, pk):
        if not _staff_ok(request.user):
            return Response({"detail": "Немає доступу"}, status=status.HTTP_403_FORBIDDEN)
        from apps.inbox.models import Conversation
        conv = Conversation.objects.select_related("channel").filter(pk=pk).first()
        allowed = request.user.allowed_channel_ids() if hasattr(request.user, "allowed_channel_ids") else None
        if not conv or (allowed is not None and conv.channel_id not in allowed):
            return Response({"detail": "Не знайдено"}, status=status.HTTP_404_NOT_FOUND)
        return Response(services.summarize(contact_id=conv.contact_id, conversation=conv))


def _clean_list(value, limit=60):
    if not isinstance(value, list):
        return None
    out = []
    for item in value[:limit]:
        s = str(item or "").strip()[:80]
        if s and s not in out:
            out.append(s)
    return out


class PhrasesView(APIView):
    """GET — поточний список фраз «ймовірно з реклами»; PUT — змінити (тільки суперюзер)."""

    def get(self, request):
        if not _staff_ok(request.user):
            return Response({"detail": "Немає доступу"}, status=status.HTTP_403_FORBIDDEN)
        cfg = services.get_phrase_config(use_cache=False)
        return Response({**cfg, "can_edit": bool(request.user.is_superuser)})

    def put(self, request):
        if not request.user.is_superuser:
            return Response({"detail": "Змінювати фрази може лише власник"}, status=status.HTTP_403_FORBIDDEN)
        cfg = services.get_phrase_config(use_cache=False)
        data = request.data if isinstance(request.data, dict) else {}
        for key in ("emoji_words", "prefixes", "phrases"):
            if key in data:
                cleaned = _clean_list(data.get(key))
                if cleaned is None:
                    return Response({"detail": "%s має бути списком рядків" % key}, status=status.HTTP_400_BAD_REQUEST)
                cfg[key] = cleaned
        if "enabled" in data:
            cfg["enabled"] = bool(data.get("enabled"))
        from apps.integrations.models import IntegrationSettings
        IntegrationSettings.objects.update_or_create(
            provider=services.PHRASES_PROVIDER, defaults={"config": cfg, "is_active": bool(cfg.get("enabled", True))})
        services.clear_phrase_cache()
        return Response({**cfg, "can_edit": True})
