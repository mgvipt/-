from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Contact
from .models import Call, CallRequest
import re
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

    @action(detail=False, methods=["post"])
    def dial(self, request):
        """Подзвонити клієнту: ставимо заявку, АТС дзвонить на внутрішній менеджера, потім клієнту."""
        number = (request.data.get("number") or "").strip()
        cid = request.data.get("contact")
        if not number and cid:
            c = Contact.objects.filter(id=cid).first()
            number = (c.phone if c else "") or ""
        number = re.sub(r"[^\d+]", "", number)
        if len(re.sub(r"\D", "", number)) < 7:
            return Response({"detail": "Немає коректного номера телефону у клієнта"}, status=status.HTTP_400_BAD_REQUEST)
        ext = (request.data.get("extension") or getattr(request.user, "extension", "") or "").strip()
        if not ext:
            return Response({"detail": "У вашому профілі не вказано внутрішній номер АТС (напр. 789). Вкажіть його, щоб дзвонити."}, status=status.HTTP_400_BAD_REQUEST)
        cr = CallRequest.objects.create(number=number, extension=str(ext),
                                        requested_by=request.user if request.user.is_authenticated else None)
        return Response({"ok": True, "id": cr.id, "number": number, "extension": ext}, status=status.HTTP_201_CREATED)


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


class OriginateQueueView(APIView):
    """Конектор FreePBX опитує чергу дзвінків і відмічає виконані. Захищено токеном."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _ok_token(self, request):
        from django.conf import settings as _s
        t = request.headers.get("X-Telephony-Token") or request.GET.get("token") or request.data.get("token")
        return bool(_s.TELEPHONY_TOKEN) and t == _s.TELEPHONY_TOKEN

    def get(self, request):
        if not self._ok_token(request):
            return Response(status=status.HTTP_403_FORBIDDEN)
        items = CallRequest.objects.filter(status="pending").order_by("created_at")[:10]
        return Response([{"id": i.id, "number": i.number, "extension": i.extension} for i in items])

    def post(self, request):
        if not self._ok_token(request):
            return Response(status=status.HTTP_403_FORBIDDEN)
        cr = CallRequest.objects.filter(id=request.data.get("id")).first()
        if cr:
            cr.status = "done" if request.data.get("ok") else "failed"
            cr.error = (request.data.get("error") or "")[:200]
            cr.save(update_fields=["status", "error"])
        return Response({"ok": True})
