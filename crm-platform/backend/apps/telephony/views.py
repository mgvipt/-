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

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if u.is_authenticated and not u.is_superuser and not u.can_see_all_deals():
            from django.db.models import Q
            qs = qs.filter(Q(manager=u) | Q(contact__owner=u) | Q(deal__owner=u))
        return qs

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
    """Приём событий о звонках от конектора FreePBX (CDR-синк).
    Захищено токеном. Розбирає напрямок (вхід/вихід), матчить клієнта по номеру.
    Очікує: external_id, direction(in|out|missed), from_number, to_number,
            duration, extension, recording, disposition, started_at, token.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    @staticmethod
    def _norm(num):
        import re
        return re.sub(r"\D", "", num or "")[-9:]   # останні 9 цифр (UA)

    def _match_contact(self, number):
        n9 = self._norm(number)
        if len(n9) < 7:
            return None
        return Contact.objects.filter(phone__endswith=n9).first()

    def post(self, request):
        from django.conf import settings as _s
        token = request.headers.get("X-Telephony-Token") or request.data.get("token", "")
        if not _s.TELEPHONY_TOKEN or token != _s.TELEPHONY_TOKEN:
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        d = request.data
        direction = d.get("direction", "in")
        frm = str(d.get("from_number", "")); to = str(d.get("to_number", ""))
        ext = str(d.get("extension", ""))
        # зовнішній (клієнтський) номер: при вихідному — кому дзвонимо, при вхідному — хто дзвонить
        external = to if direction == "out" else frm
        contact = self._match_contact(external)
        deal = None
        if contact:
            from apps.crm.models import Deal
            deal = (Deal.objects.filter(contact=contact).exclude(stage__is_lost=True)
                    .order_by("-created_at").first())

        defaults = dict(
            direction=direction, from_number=frm, to_number=to,
            duration=int(d.get("duration", 0) or 0),
            recording_file=d.get("recording", "") or "",
            disposition=d.get("disposition", "") or "",
            extension=ext, contact=contact, deal=deal,
        )
        sa = d.get("started_at")
        if sa:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(sa)
            if dt:
                defaults["started_at"] = dt

        ext_id = d.get("external_id", "")
        if ext_id:
            call, created = Call.objects.update_or_create(external_id=ext_id, defaults=defaults)
        else:
            call, created = Call.objects.create(**defaults), True
        return Response({"ok": True, "id": call.id, "created": created,
                         "matched_contact": bool(contact)}, status=status.HTTP_201_CREATED)
