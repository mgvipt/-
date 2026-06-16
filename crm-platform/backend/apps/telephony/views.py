from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Contact
from .models import Call
from .serializers import CallSerializer


class CallViewSet(viewsets.ModelViewSet):
    queryset = Call.objects.select_related("manager", "contact", "deal")
    serializer_class = CallSerializer
    filterset_fields = ["direction", "manager", "deal", "contact"]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = Call.objects.all()
        total = qs.count()
        recorded = qs.exclude(recording_url="").count()
        missed = qs.filter(direction="missed").count()
        avg = qs.aggregate(s=Sum("duration"))["s"] or 0
        avg = int(avg / total) if total else 0
        return Response({"total": total, "recorded": recorded, "missed": missed,
                         "avg_seconds": avg})


class CallWebhookView(APIView):
    """Приём событий от SIP-шлюза (Asterisk) после звонка: создаёт запись в журнале.
    Ожидает: direction, from_number, to_number, duration, recording_url, external_id.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        d = request.data
        phone = d.get("from_number") or d.get("to_number") or ""
        contact = Contact.objects.filter(phone=phone).first()
        Call.objects.create(
            direction=d.get("direction", "in"),
            from_number=d.get("from_number", ""), to_number=d.get("to_number", ""),
            duration=int(d.get("duration", 0) or 0),
            recording_url=d.get("recording_url", ""),
            external_id=d.get("external_id", ""), contact=contact,
        )
        return Response({"ok": True}, status=status.HTTP_201_CREATED)
