"""Особистий асистент — API. Усе лише для власника (is_superuser); приймання — лише з секретом бота."""
import hmac
import json
import os

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services as svc
from .models import AssistantChat, AssistantMessage, AssistantProposal, AssistantSettings


def _iso(v):
    return timezone.localtime(v).isoformat() if v else None


class _Owner(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not request.user.is_superuser:
            self.permission_denied(request, message="Особистий асистент доступний лише власнику.")


class IngestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = os.environ.get("CF_INGEST_SECRET", "")
        if not secret or not hmac.compare_digest(request.headers.get("X-CF-Ingest", ""), secret):
            return Response({"error": "forbidden"}, status=403)
        try:
            update = request.data if isinstance(request.data, dict) else json.loads(request.body or b"{}")
        except ValueError:
            return Response({"error": "bad json"}, status=400)
        if update.get("business_connection"):
            return Response({"status": svc.connection(update)})
        return Response({"status": svc.ingest(update)})


def _proposal(p):
    return {"id": p.id, "kind": p.kind, "kind_display": p.get_kind_display(), "title": p.title, "text": p.text,
            "who": p.who, "due": p.due.isoformat() if p.due else None, "chat": p.chat.title if p.chat_id else "",
            "evidence": p.evidence, "status": p.status, "knowledge_item_id": p.knowledge_item_id,
            "created_at": _iso(p.created_at)}


class AssistantView(_Owner):
    def get(self, request):
        s = AssistantSettings.get()
        status = request.GET.get("status", "new")
        qs = AssistantProposal.objects.select_related("chat")
        if status != "all":
            qs = qs.filter(status=status)
        if request.GET.get("kind"):
            qs = qs.filter(kind=request.GET["kind"])
        chats = AssistantChat.objects.annotate(
            n=Count("messages"), voice=Count("messages", filter=Q(messages__kind__in=["voice", "video_note"])),
            fresh=Count("messages", filter=Q(messages__processed_at=None)))
        return Response({
            "settings": {"extraction_enabled": s.extraction_enabled, "monthly_budget_usd": float(s.monthly_budget_usd),
                         "spent_month_usd": round(svc.month_spent(), 4), "owner_connected": bool(s.owner_tg_id)},
            "chats": [{"id": c.id, "title": c.title, "kind": c.kind, "kind_display": c.get_kind_display(),
                       "enabled": c.enabled, "messages": c.n, "voice": c.voice, "fresh": c.fresh} for c in chats],
            "counts": dict(AssistantProposal.objects.values_list("status").annotate(n=Count("id"))),
            "proposals": [_proposal(p) for p in qs[:100]],
            "agreements": [_proposal(p) for p in AssistantProposal.objects.select_related("chat").filter(
                kind=AssistantProposal.Kind.AGREEMENT, status=AssistantProposal.Status.ACCEPTED).order_by("due", "-created_at")[:50]],
            "pending_voice": AssistantMessage.objects.filter(kind__in=["voice", "video_note"], transcribed_at=None).count(),
        })

    def patch(self, request):
        s, data = AssistantSettings.get(), request.data or {}
        if "extraction_enabled" in data:
            s.extraction_enabled = bool(data["extraction_enabled"])
        if "monthly_budget_usd" in data:
            try:
                b = round(float(data["monthly_budget_usd"]), 2)
            except (TypeError, ValueError):
                return Response({"error": "Ліміт має бути числом."}, status=400)
            if not 0 <= b <= 50:
                return Response({"error": "Ліміт — від $0 до $50."}, status=400)
            s.monthly_budget_usd = b
        s.save()
        return self.get(request)

    def post(self, request):
        """{"action": "transcribe" | "extract"} — запустити зараз (платно, в межах ліміту)."""
        action = (request.data or {}).get("action")
        try:
            n = svc.transcribe_pending() if action == "transcribe" else svc.extract() if action == "extract" else None
        except svc.BudgetError as e:
            return Response({"error": str(e)}, status=402)
        if n is None:
            return Response({"error": "Невідома дія."}, status=400)
        return Response({"done": n})


class ChatView(_Owner):
    def patch(self, request, pk):
        c = get_object_or_404(AssistantChat, pk=pk)
        c.enabled = bool((request.data or {}).get("enabled"))
        c.save(update_fields=["enabled"])
        return Response({"id": c.id, "enabled": c.enabled})

    def get(self, request, pk):
        """Останні повідомлення чату — щоб перевірити, що асистент чує правильно."""
        c = get_object_or_404(AssistantChat, pk=pk)
        msgs = list(c.messages.order_by("-sent_at")[:80])[::-1]
        return Response({"title": c.title, "messages": [
            {"id": m.id, "from_owner": m.from_owner, "author": m.author, "kind": m.kind, "body": m.body,
             "sent_at": _iso(m.sent_at)} for m in msgs]})


class ProposalView(_Owner):
    def patch(self, request, pk):
        p = get_object_or_404(AssistantProposal, pk=pk)
        data = request.data or {}
        for f in ("title", "text", "who"):
            if f in data:
                setattr(p, f, str(data[f] or "")[:4000 if f == "text" else 200])
        p.save()
        st = data.get("status")
        if st == AssistantProposal.Status.ACCEPTED:
            svc.accept(p)
        elif st in (AssistantProposal.Status.REJECTED, AssistantProposal.Status.NEW):
            p.status = st
            p.save(update_fields=["status"])
        return Response(_proposal(p))
