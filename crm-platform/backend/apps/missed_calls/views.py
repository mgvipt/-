"""API черги «Пропущені» (/api/telephony/missed/…). GET — лише читання; дії — POST."""
from datetime import date, datetime, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import MissedCallItem, MissedCallSettings


def _colleagues():
    """Кому можна передати: лише ті, хто бачить чергу (право «Доступ до телефонії»)."""
    ok = services.eligible_ids()
    return [{"id": u.id, "name": services.user_name(u), "extension": u.extension or ""}
            for u in services._staff_qs().filter(id__in=ok).order_by("first_name", "last_name", "username")]


class MissedListView(APIView):
    """Черга: ?status=open|closed|all (типово open), ?scope=mine|all, ?days=N (для закритих, типово 3)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        if not services.can_use(u):
            return Response({"detail": "Немає доступу до телефонії"}, status=status.HTTP_403_FORBIDDEN)
        cfg = MissedCallSettings.get()
        cal = services.calendar(cfg)
        now = timezone.now()
        scope = request.GET.get("scope") or ("all" if services.can_all(u) else "mine")
        st = request.GET.get("status") or "open"
        qs = services.visible_qs(u, scope)
        if st == "open":
            qs = qs.filter(status="open").order_by("first_missed_at", "id")
        else:
            try:
                days = max(1, min(60, int(request.GET.get("days") or 3)))
            except ValueError:
                days = 3
            qs = qs.filter(first_missed_at__gte=now - timedelta(days=days))
            if st == "closed":
                qs = qs.filter(status="closed")
            qs = qs.order_by("-first_missed_at", "-id")
        items = [services.serialize(it, now, cal, cfg) for it in qs[:200]]
        base = MissedCallItem.objects.filter(status="open")
        counts = {"mine": base.filter(assignee=u).count(), "unassigned": base.filter(assignee__isnull=True).count(),
                  "all": base.count() if services.can_all(u) else None}
        return Response({
            "results": items, "counts": counts, "scope": scope, "status": st,
            "can_all": services.can_all(u), "can_report": services.can_report(u),
            "can_settings": services.can_settings(u), "colleagues": _colleagues(),
            "sla_minutes": cfg.sla_minutes, "escalate_minutes": cfg.escalate_minutes,
        })


class MissedSummaryView(APIView):
    """Лічильник і нові пропущені для віджета телефона. Лише читання."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.summary(request.user))


class MissedActionView(APIView):
    """POST {action: "close", reason: other_channel|not_relevant, note} | {action: "transfer", user_id, note}."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        u = request.user
        item = get_object_or_404(MissedCallItem, pk=pk)
        if not services.can_use(u) or not services.can_touch(u, item):
            return Response({"detail": "Це пропущений іншого менеджера"}, status=status.HTTP_403_FORBIDDEN)
        act = request.data.get("action")
        note = str(request.data.get("note") or "")
        if act == "close":
            reason = request.data.get("reason")
            if reason not in ("other_channel", "not_relevant"):
                return Response({"detail": "Невідома причина"}, status=status.HTTP_400_BAD_REQUEST)
            item = services.close_manual(item, reason, u, note)
        elif act == "transfer":
            try:
                uid = int(request.data.get("user_id"))
            except (TypeError, ValueError):
                uid = 0
            to = services._staff_qs().filter(id=uid).first() if uid in services.eligible_ids() else None
            if not to:
                return Response({"detail": "Оберіть колегу"}, status=status.HTTP_400_BAD_REQUEST)
            if item.status != "open":
                return Response({"detail": "Вже оброблено"}, status=status.HTTP_400_BAD_REQUEST)
            item = services.transfer(item, to, u, note)
        else:
            return Response({"detail": "Невідома дія"}, status=status.HTTP_400_BAD_REQUEST)
        cfg = MissedCallSettings.get()
        item = MissedCallItem.objects.select_related("assignee", "contact").get(pk=item.pk)
        return Response(services.serialize(item, timezone.now(), services.calendar(cfg), cfg))


def _parse_date(v, default):
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date() if v else default
    except ValueError:
        return default


class MissedReportView(APIView):
    """Звіт ?from=YYYY-MM-DD&to=YYYY-MM-DD (типово останні 30 днів)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not services.can_report(request.user):
            return Response({"detail": "Немає права на звіт"}, status=status.HTTP_403_FORBIDDEN)
        today = timezone.localdate()
        d_to = _parse_date(request.GET.get("to"), today)
        d_from = _parse_date(request.GET.get("from"), d_to - timedelta(days=29))
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        if (d_to - d_from).days > 370:
            d_from = d_to - timedelta(days=370)
        return Response(services.report(d_from, d_to))


class MissedSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _payload(cfg, u):
        return {
            "work_start": cfg.work_start.strftime("%H:%M"), "work_end": cfg.work_end.strftime("%H:%M"),
            "work_days": cfg.work_days or [0, 1, 2, 3, 4, 5, 6],
            "sla_minutes": cfg.sla_minutes, "escalate_minutes": cfg.escalate_minutes,
            "escalate_user_ids": cfg.escalate_user_ids or [], "auto_task": cfg.auto_task,
            "ignore_numbers": cfg.ignore_numbers or [], "ignore_staff_numbers": cfg.ignore_staff_numbers,
            "active_since": cfg.active_since, "can_edit": services.can_settings(u),
            "escalate_default": [{"id": x.id, "name": services.user_name(x)} for x in services.escalation_targets(cfg)],
        }

    def get(self, request):
        u = request.user
        if not (services.can_settings(u) or services.can_report(u)):
            return Response({"detail": "Немає доступу"}, status=status.HTTP_403_FORBIDDEN)
        return Response(self._payload(MissedCallSettings.get(), u))

    def patch(self, request):
        u = request.user
        if not services.can_settings(u):
            return Response({"detail": "Змінювати може власник або хто керує чергою"}, status=status.HTTP_403_FORBIDDEN)
        cfg = MissedCallSettings.get()
        d = request.data
        try:
            for f in ("work_start", "work_end"):
                if f in d:
                    setattr(cfg, f, datetime.strptime(str(d[f])[:5], "%H:%M").time())
            if "work_days" in d:
                cfg.work_days = sorted({int(x) for x in (d["work_days"] or []) if 0 <= int(x) <= 6})
            if "sla_minutes" in d:
                cfg.sla_minutes = max(1, min(600, int(d["sla_minutes"])))
            if "escalate_minutes" in d:
                cfg.escalate_minutes = max(5, min(2400, int(d["escalate_minutes"])))
            if "escalate_user_ids" in d:
                cfg.escalate_user_ids = [int(x) for x in (d["escalate_user_ids"] or [])][:10]
            if "auto_task" in d:
                cfg.auto_task = bool(d["auto_task"])
            if "ignore_staff_numbers" in d:
                cfg.ignore_staff_numbers = bool(d["ignore_staff_numbers"])
            if "ignore_numbers" in d:
                raw = d["ignore_numbers"]
                if isinstance(raw, str):
                    raw = raw.replace(";", ",").replace("\n", ",").split(",")
                cfg.ignore_numbers = [x.strip() for x in raw if len("".join(ch for ch in str(x) if ch.isdigit())) >= 7][:100]
        except (TypeError, ValueError):
            return Response({"detail": "Некоректне значення"}, status=status.HTTP_400_BAD_REQUEST)
        if cfg.work_end <= cfg.work_start:
            return Response({"detail": "Кінець дня має бути пізніше за початок"}, status=status.HTTP_400_BAD_REQUEST)
        cfg.save()
        return Response(self._payload(cfg, u))
