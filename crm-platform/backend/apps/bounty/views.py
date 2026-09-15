"""API «Біржа задач» (/api/bounty/…). Права — див. services.py (bounty.view за замовчуванням у всіх співробітників,
bounty.manage — прайс і прийняття; призначений перевіряючий приймає лише свої позиції)."""
from django.db import transaction
from django.http import HttpResponse
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services as S
from .models import DEPARTMENT_LABELS, ClaimFile, TaskCategory, TaskClaim, TaskOffer


def _err(e):
    return Response({"detail": e.detail, "code": e.code, **e.extra}, status=e.status)


def _deny(text="Немає доступу до біржі задач"):
    return Response({"detail": text}, status=403)


class _Base(APIView):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, S.BountyError):
            return _err(exc)
        return super().handle_exception(exc)


class BoardView(_Base):
    """GET — усе для екрана: відділи, напрями, задачі з станом («вільно / зайнято / ліміт»), мій стандарт, фонд."""

    def get(self, request):
        if not S.can_view(request.user):
            return _deny()
        return Response(S.board(request.user))


class CategoriesView(_Base):
    def post(self, request):
        if not S.can_manage(request.user):
            return _deny("Змінювати прайс може власник («Керувати біржею задач»)")
        d = request.data
        dep = d.get("department")
        name = str(d.get("name") or "").strip()
        if dep not in DEPARTMENT_LABELS:
            raise S.BountyError("Оберіть відділ")
        if not name:
            raise S.BountyError("Назва напряму обовʼязкова")
        c = TaskCategory.objects.create(department=dep, name=name[:120], active=S.to_bool(d.get("active", True)),
                                        order=S.next_order(TaskCategory, department=dep))
        return Response(S.category_json(c), status=201)


class CategoryDetailView(_Base):
    def patch(self, request, pk):
        if not S.can_manage(request.user):
            return _deny("Змінювати прайс може власник («Керувати біржею задач»)")
        c = TaskCategory.objects.filter(pk=pk, archived=False).first()
        if not c:
            raise S.BountyError("Напрям не знайдено", 404)
        d = request.data
        if "name" in d:
            name = str(d.get("name") or "").strip()
            if not name:
                raise S.BountyError("Назва напряму обовʼязкова")
            c.name = name[:120]
        if "department" in d:
            if d["department"] not in DEPARTMENT_LABELS:
                raise S.BountyError("Оберіть відділ")
            c.department = d["department"]
        if "active" in d:
            c.active = S.to_bool(d.get("active"))
        if "order" in d:
            c.order = S.to_int(d.get("order"), "Порядок", 0, 1000000)
        c.save()
        return Response(S.category_json(c))

    def delete(self, request, pk):
        """Мʼяке видалення: напрям і його задачі — в архів; взяті задачі доробляються і приймаються як звичайно."""
        if not S.can_manage(request.user):
            return _deny("Змінювати прайс може власник («Керувати біржею задач»)")
        c = TaskCategory.objects.filter(pk=pk, archived=False).first()
        if not c:
            raise S.BountyError("Напрям не знайдено", 404)
        with transaction.atomic():
            n = TaskOffer.objects.filter(category=c, archived=False).update(archived=True, active=False)
            c.archived = True
            c.active = False
            c.save(update_fields=["archived", "active"])
        return Response({"ok": True, "archived_offers": n})


class CategoryMoveView(_Base):
    def post(self, request, pk):
        if not S.can_manage(request.user):
            return _deny()
        c = TaskCategory.objects.filter(pk=pk, archived=False).first()
        if not c:
            raise S.BountyError("Напрям не знайдено", 404)
        S.move(c, "up" if request.data.get("dir") == "up" else "down")
        return Response({"ok": True})


class OffersView(_Base):
    def post(self, request):
        if not S.can_manage(request.user):
            return _deny("Змінювати прайс може власник («Керувати біржею задач»)")
        o = TaskOffer(created_by=request.user)
        S.apply_offer_fields(o, request.data, partial=False)
        if "order" not in request.data:
            o.order = S.next_order(TaskOffer, category_id=o.category_id)
        o.save()
        return Response(S.offer_json(o), status=201)


class OfferDetailView(_Base):
    def patch(self, request, pk):
        if not S.can_manage(request.user):
            return _deny("Змінювати прайс може власник («Керувати біржею задач»)")
        o = TaskOffer.objects.filter(pk=pk).select_related("category").first()
        if not o:
            raise S.BountyError("Задачу не знайдено", 404)
        S.apply_offer_fields(o, request.data, partial=True)
        o.save()
        return Response(S.offer_json(o))

    def delete(self, request, pk):
        """Мʼяке видалення (архів). Уже взяті задачі доробляються і приймаються як звичайно."""
        if not S.can_manage(request.user):
            return _deny("Змінювати прайс може власник («Керувати біржею задач»)")
        n = TaskOffer.objects.filter(pk=pk).update(archived=True, active=False)
        if not n:
            raise S.BountyError("Задачу не знайдено", 404)
        return Response({"ok": True, "in_work": TaskClaim.objects.filter(offer_id=pk, status__in=S.ACTIVE).count()})


class OfferRestoreView(_Base):
    def post(self, request, pk):
        if not S.can_manage(request.user):
            return _deny()
        o = TaskOffer.objects.filter(pk=pk, archived=True).select_related("category").first()
        if not o:
            raise S.BountyError("Задачу не знайдено в архіві", 404)
        if o.category.archived:
            raise S.BountyError("Спершу відновіть напрям — його видалено")
        o.archived = False
        o.active = False
        o.save(update_fields=["archived", "active", "updated_at"])
        return Response(S.offer_json(o))


class OfferMoveView(_Base):
    def post(self, request, pk):
        if not S.can_manage(request.user):
            return _deny()
        o = TaskOffer.objects.filter(pk=pk, archived=False).first()
        if not o:
            raise S.BountyError("Задачу не знайдено", 404)
        S.move(o, "up" if request.data.get("dir") == "up" else "down")
        return Response({"ok": True})


class ActivateView(_Base):
    """POST {department | category_id, active} — увімкнути / вимкнути весь відділ або напрям однією кнопкою."""

    def post(self, request):
        if not S.can_manage(request.user):
            return _deny("Вмикати задачі може власник («Керувати біржею задач»)")
        d = request.data
        on = S.to_bool(d.get("active", True))
        offers = TaskOffer.objects.filter(archived=False)
        cats = TaskCategory.objects.filter(archived=False)
        if d.get("category_id"):
            offers = offers.filter(category_id=d["category_id"])
            cats = cats.filter(pk=d["category_id"])
        elif d.get("department") in DEPARTMENT_LABELS:
            offers = offers.filter(category__department=d["department"])
            cats = cats.filter(department=d["department"])
        else:
            raise S.BountyError("Оберіть відділ або напрям")
        with transaction.atomic():
            n = offers.update(active=on)
            if on:
                cats.update(active=True)
        return Response({"ok": True, "changed": n, "active": on})


class TakeView(_Base):
    def post(self, request, pk):
        c, warning = S.take(pk, request.user, request.data.get("qty"))
        return Response({"claim": S.claim_json(S.claims_qs().get(pk=c.pk), request.user), "warning": warning}, status=201)


class ClaimsView(_Base):
    """GET ?scope=mine|review|all&status=&month=YYYY-MM&user_id="""

    def get(self, request):
        if not S.can_view(request.user):
            return _deny()
        p = request.query_params
        uid = p.get("user_id")
        return Response({"results": S.list_claims(request.user, p.get("scope") or "mine", p.get("status") or "",
                                                  p.get("month") or "", int(uid) if uid and uid.isdigit() else None)})


class ClaimActionView(_Base):
    """POST /claims/<id>/submit|accept|rework|cancel|subtasks/  (subtasks: {"done": [0, 2]} — відмітки виконавця)"""

    def post(self, request, pk, act):
        u, d = request.user, request.data
        if not S.can_view(u) and act != "cancel":
            return _deny()
        if act == "submit":
            c = S.submit(pk, u, d.get("proof_text", ""), d.get("proof_url", ""), d.get("qty"))
        elif act == "accept":
            c = S.accept(pk, u, qty=d.get("qty"), base_amount=d.get("base_amount"), amount=d.get("amount"),
                         quality=d.get("quality"), comment=d.get("comment", ""), period=d.get("payroll_period") or None,
                         force=S.to_bool(d.get("force")))
        elif act == "rework":
            c = S.rework(pk, u, d.get("comment", ""))
        elif act == "cancel":
            c = S.cancel(pk, u, d.get("comment", ""))
        elif act == "subtasks":
            c = S.set_subtasks(pk, u, d.get("done"))
        else:
            raise S.BountyError("Невідома дія", 404)
        return Response(S.claim_json(S.claims_qs().get(pk=c.pk), u))


class ClaimFilesView(_Base):
    """POST multipart file — фото/файл-доказ до своєї задачі (до здачі або на доробці). До 10 МБ, до 10 файлів."""
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        c = TaskClaim.objects.filter(pk=pk).first()
        if not c:
            raise S.BountyError("Задачу не знайдено", 404)
        if c.user_id != request.user.id:
            return _deny("Додати доказ може лише той, хто взяв задачу")
        if c.status not in ("taken", "rework"):
            raise S.BountyError("Задачу вже здано — файл не додати", 409)
        f = request.FILES.get("file")
        if not f:
            raise S.BountyError("Немає файлу")
        if f.size > S.MAX_FILE:
            raise S.BountyError("Файл більший за 10 МБ — стисніть або дайте посилання")
        if c.files.count() >= S.MAX_FILES:
            raise S.BountyError("Не більше 10 файлів — решту посиланням на папку")
        a = ClaimFile.objects.create(claim=c, filename=(f.name or "file")[:255],
                                     content_type=(f.content_type or "application/octet-stream")[:120],
                                     size=f.size, data=f.read(), uploaded_by=request.user)
        return Response({"id": a.id, "filename": a.filename, "content_type": a.content_type, "size": a.size}, status=201)


class FileView(_Base):
    def _get(self, request, pk):
        a = ClaimFile.objects.select_related("claim__offer").filter(pk=pk).first()
        if not a:
            raise S.BountyError("Файл не знайдено", 404)
        u = request.user
        if not (a.claim.user_id == u.id or S.can_manage(u) or S.can_review(u, a.claim)):
            raise S.BountyError("Немає доступу до файлу", 403)
        return a

    def get(self, request, pk):
        a = self._get(request, pk)
        resp = HttpResponse(bytes(a.data), content_type=a.content_type)
        resp["Content-Disposition"] = 'inline; filename="%s"' % a.filename.replace('"', "")
        return resp

    def delete(self, request, pk):
        a = self._get(request, pk)
        if not (a.claim.user_id == request.user.id and a.claim.status in ("taken", "rework")):
            raise S.BountyError("Видалити файл може виконавець до здачі задачі", 403)
        a.delete()
        return Response(status=204)


class SummaryView(_Base):
    def get(self, request):
        if not S.can_view(request.user):
            return _deny()
        m = request.query_params.get("month") or S.month_of()
        if not S.valid_period(m):
            raise S.BountyError("Місяць у форматі РРРР-ММ")
        return Response(S.summary(request.user, m))
