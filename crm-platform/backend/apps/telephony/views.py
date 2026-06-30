from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Contact
from .models import Call, CallRequest, RingingCall
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
        qs = self.get_queryset()
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
        if request.data.get("resolve_only"):
            return Response({"ok": True, "number": number})
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
            line=d.get("line", "") or "",
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


class RingingView(APIView):
    """АТС повідомляє: дзвінок задзвонив / завершився. Захищено токеном."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings as _s
        t = request.headers.get("X-Telephony-Token") or request.data.get("token")
        if not _s.TELEPHONY_TOKEN or t != _s.TELEPHONY_TOKEN:
            return Response(status=status.HTTP_403_FORBIDDEN)
        d = request.data
        uid = str(d.get("uniqueid", ""))
        if not uid:
            return Response({"ok": False})
        if d.get("action") == "end":
            RingingCall.objects.filter(uniqueid=uid).update(active=False)
            return Response({"ok": True})
        number = str(d.get("number", ""))
        n9 = re.sub(r"\D", "", number)[-9:]
        contact = Contact.objects.filter(phone__endswith=n9).first() if len(n9) >= 7 else None
        RingingCall.objects.update_or_create(uniqueid=uid, defaults={
            "number": number, "line": d.get("line", "") or "", "contact": contact, "active": True})
        return Response({"ok": True, "matched": bool(contact)})


class RingingActiveView(APIView):
    """Фронт опитує: чи є зараз вхідний дзвінок (показати спливашку)."""
    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(seconds=45)
        qs = (RingingCall.objects.filter(active=True, created_at__gte=cutoff)
              .select_related("contact").order_by("-created_at")[:5])
        return Response([{
            "uniqueid": r.uniqueid, "number": r.number, "line": r.line,
            "contact": r.contact_id, "contact_name": (str(r.contact) if r.contact else ""),
        } for r in qs])


class WebrtcConfigView(APIView):
    """Параметри веб-телефона для браузера (тільки залогіненим)."""
    def get(self, request):
        from django.conf import settings as _s
        ext = getattr(request.user, "extension", "") or _s.TELEPHONY_WEBRTC_EXT
        return Response({
            "ws": _s.TELEPHONY_WS,
            "ext": _s.TELEPHONY_WEBRTC_EXT,           # SIP-логін веб-телефона (поки спільний 700)
            "secret": _s.TELEPHONY_WEBRTC_SECRET,
            "my_ext": ext,
            "enabled": bool(_s.TELEPHONY_WS and _s.TELEPHONY_WEBRTC_SECRET),
        })


class RecordingView(APIView):
    """Стрім запису дзвінка (підписаний URL — для <audio>/посилання без DRF-хедера)."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, pk):
        import os, hmac, hashlib
        from django.conf import settings as _s
        from django.http import FileResponse, Http404, HttpResponseForbidden
        call = Call.objects.filter(pk=pk).first()
        if not call or not call.recording_file:
            raise Http404("no recording")
        good = hmac.new(_s.SECRET_KEY.encode(), str(pk).encode(), hashlib.sha256).hexdigest()[:20]
        if request.GET.get("s") != good:
            return HttpResponseForbidden("bad sig")
        path = os.path.join("/app/media/recordings", call.recording_file)
        if not os.path.exists(path):
            raise Http404("file missing")
        return FileResponse(open(path, "rb"), content_type="audio/wav")


class PendingTranscribeView(APIView):
    """Список дзвінків що чекають транскрипцію (для хост-скрипта Whisper)."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings as _s
        token = request.headers.get("X-Telephony-Token") or request.GET.get("token", "")
        if not _s.TELEPHONY_TOKEN or token != _s.TELEPHONY_TOKEN:
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            lim = int(request.GET.get("limit", 5))
        except Exception:
            lim = 5
        qs = (Call.objects.filter(analyzed=False, duration__gte=15)
              .exclude(recording_file="").order_by("-started_at", "-id")[:lim])
        return Response([{"id": c.id, "recording_file": c.recording_file} for c in qs])


class TranscribeView(APIView):
    """Приймає транскрипт дзвінка → зберігає + запускає AI-розбір (DialogAnalysis kind=call)."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings as _s
        token = request.headers.get("X-Telephony-Token") or request.data.get("token", "")
        if not _s.TELEPHONY_TOKEN or token != _s.TELEPHONY_TOKEN:
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        call = Call.objects.filter(pk=request.data.get("call_id")).first()
        if not call:
            return Response({"detail": "no call"}, status=status.HTTP_404_NOT_FOUND)
        raw = (request.data.get("transcript") or "")[:20000]
        from apps.crm.sales_analyst import label_speakers
        txt = label_speakers(raw) if len(raw.strip()) >= 30 else raw
        call.transcript = txt
        call.analyzed = True
        call.save(update_fields=["transcript", "analyzed"])
        if len(txt.strip()) >= 40:
            try:
                from apps.crm.sales_analyst import analyze_dialog
                from apps.crm.models import DialogAnalysis
                mgr_id = None
                if call.deal_id and call.deal and call.deal.owner_id:
                    mgr_id = call.deal.owner_id
                elif call.manager_id:
                    mgr_id = call.manager_id
                msgs = []
                for ln in txt.split(chr(10)):
                    ln = ln.strip()
                    if ln.startswith("\u041a\u041b\u0406\u0404\u041d\u0422:"):
                        msgs.append({"direction": "in", "text": ln.split(":", 1)[1].strip()})
                    elif ln.startswith("\u041c\u0415\u041d\u0415\u0414\u0416\u0415\u0420:"):
                        msgs.append({"direction": "out", "text": ln.split(":", 1)[1].strip()})
                if not msgs:
                    msgs = [{"direction": "note", "text": txt}]
                r = analyze_dialog(msgs, context=f"\u0422\u0435\u043b\u0435\u0444\u043e\u043d\u043d\u0438\u0439 \u0434\u0437\u0432\u0456\u043d\u043e\u043a ({call.direction}), \u043b\u0456\u043d\u0456\u044f {call.line}", kind="\u0434\u0437\u0432\u0456\u043d\u043e\u043a")
                if isinstance(r, dict) and not r.get("empty"):
                    _da = DialogAnalysis.objects.create(
                        deal_id=call.deal_id, manager_id=mgr_id, kind="call",
                        overall_score=r.get("overall", 0) or 0, scores=r.get("scores", {}) or {},
                        strengths=r.get("strengths", ""), why_not_selling=r.get("why_not_selling", ""),
                        recommended_reply=r.get("recommended_reply", ""), coaching=r.get("coaching", ""))
                    if call.started_at:
                        from apps.gamification.models import XPEvent as _XP
                        DialogAnalysis.objects.filter(pk=_da.pk).update(created_at=call.started_at)
                        _XP.objects.filter(ref_type="analysis", ref_id=str(_da.pk)).update(created_at=call.started_at)
            except Exception:
                pass
        return Response({"ok": True})
