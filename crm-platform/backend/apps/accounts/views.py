from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import User, Role, Department, Invite, PERMISSION_CHOICES
from .serializers import UserSerializer, RoleSerializer, MeSerializer, DepartmentSerializer, InviteSerializer
from apps.common.permissions import HasPermCode


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all().order_by("name")
    serializer_class = RoleSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"


def _rr_reassign(qs, field, pool):
    """Round-robin: розподілити записи qs рівномірно між pool (список юзерів). Повертає к-сть."""
    ids = list(qs.values_list("id", flat=True))
    if not pool or not ids:
        return 0
    nn = len(pool)
    for i, p in enumerate(pool):
        chunk = ids[i::nn]
        if chunk:
            qs.model.objects.filter(id__in=chunk).update(**{field: p})
    return len(ids)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("role", "department").order_by("username")
    serializer_class = UserSerializer
    permission_classes = [HasPermCode]

    def get_queryset(self):
        """Фільтр за статусом занятості: ?status=active|inactive|dismissed|all.
        За замовчуванням (без параметра) — тільки активні (сумісність зі старим фронтом).
        ⚠️ Тільки для списку — detail-дії (set_status/dismiss/patch) мусять бачити ВСІХ,
        інакше повернення звільненого/неактивного дає 404."""
        qs = super().get_queryset()
        if self.action != "list":
            return qs
        st = (self.request.query_params.get("status") or "").strip().lower()
        if st in ("active", "inactive", "dismissed"):
            return qs.filter(employment_status=st)
        if st == "all":
            return qs
        # дефолт: активні (включно зі старими записами де employment_status ще 'active' за замовч.)
        return qs.filter(is_active=True)

    # поля картки, які можна редагувати (решта — тільки через адмінку/права)
    PROFILE_FIELDS = ["photo", "position", "birthday", "about", "interests", "telegram", "phone"]

    def get_permissions(self):
        # свою картку співробітник редагує сам — без права roles.manage
        if getattr(self, "action", None) == "profile":
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=True, methods=["patch"])
    def profile(self, request, pk=None):
        """Картка співробітника: свою редагує сам, чужу — адмін / roles.manage."""
        u = User.objects.filter(pk=pk).first()
        if not u:
            return Response({"detail": "Немає такого"}, status=status.HTTP_404_NOT_FOUND)
        actor = request.user
        is_admin = actor.is_superuser or (hasattr(actor, "has_perm_code") and actor.has_perm_code("roles.manage"))
        if u.id != actor.id and not is_admin:
            return Response({"detail": "Можна редагувати лише свою картку"}, status=status.HTTP_403_FORBIDDEN)
        data = {f: request.data[f] for f in self.PROFILE_FIELDS if f in request.data}
        if not data:
            return Response(UserSerializer(u, context={"request": request}).data)
        # фото зберігається як data URL у БД — обмежуємо розмір (фронт стискає до 256px)
        if data.get("photo") and len(str(data["photo"])) > 400000:
            return Response({"detail": "Фото завелике — стисніть зображення"}, status=status.HTTP_400_BAD_REQUEST)
        if "birthday" in data and not data["birthday"]:
            data["birthday"] = None
        for k, v in data.items():
            setattr(u, k, v)
        u.save(update_fields=list(data.keys()))
        return Response(UserSerializer(u, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        """Змінити статус занятості: active / inactive / dismissed. Лише адмін / roles.manage.
        Для 'dismissed' краще використовувати /dismiss/ (він ще й розподіляє сутності)."""
        actor = request.user
        if not (actor.is_superuser or (hasattr(actor, "has_perm_code") and actor.has_perm_code("roles.manage"))):
            return Response({"detail": "Лише адмін може змінювати статус"}, status=status.HTTP_403_FORBIDDEN)
        u = self.get_object()
        new_status = (request.data.get("status") or "").strip().lower()
        if new_status not in dict(User.EMPLOYMENT_STATUS):
            return Response({"detail": "Невідомий статус"}, status=status.HTTP_400_BAD_REQUEST)
        if u.id == actor.id and new_status != "active":
            return Response({"detail": "Не можна деактивувати себе"}, status=status.HTTP_400_BAD_REQUEST)
        old = u.employment_status
        u.apply_employment_status(new_status)
        try:
            from apps.crm.models import log_activity
            log_activity("contact", 0, "Зміна статусу співробітника",
                         "%s: %s → %s" % (u.get_full_name() or u.username, old, new_status), actor, "Адмін")
        except Exception:
            pass
        return Response({"ok": True, "employment_status": u.employment_status,
                         "is_active": u.is_active, "dismissed_at": u.dismissed_at})

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        """Звільнення: акаунт деактивується (доступ зникає, НЕ видаляється), а його сутності
        переходять: продажник → round-robin на всіх активних продажників; інший відділ →
        керівнику відділу (він розподілить), або round-robin на активних членів відділу."""
        actor = request.user
        if not (actor.is_superuser or (hasattr(actor, "has_perm_code") and actor.has_perm_code("roles.manage"))):
            return Response({"detail": "Лише адмін може звільняти"}, status=status.HTTP_403_FORBIDDEN)
        u = self.get_object()
        if u.id == actor.id:
            return Response({"detail": "Не можна звільнити себе"}, status=status.HTTP_400_BAD_REQUEST)
        from apps.crm.models import Deal, Lead, Contact, Task
        from apps.inbox.models import Conversation
        from apps.warehouse.models import WarehouseJob
        from apps.crm.lead_routing import lead_owner_pool
        dept = u.department
        is_sales = bool(dept and "продаж" in (dept.name or "").lower())
        moved = {}
        if is_sales:
            pool = [p for p in lead_owner_pool() if p.id != u.id]
            if not pool:
                pool = list(User.objects.filter(is_active=True, is_superuser=False).exclude(id=u.id)[:10])
            moved["клиенты"] = _rr_reassign(Contact.objects.filter(owner=u), "owner", pool)
            moved["лиды"] = _rr_reassign(Lead.objects.filter(owner=u), "owner", pool)
            moved["сделки"] = _rr_reassign(Deal.objects.filter(owner=u), "owner", pool)
            moved["чаты"] = _rr_reassign(Conversation.objects.filter(assigned_to=u), "assigned_to", pool)
        else:
            head = dept.head if (dept and dept.head_id and dept.head_id != u.id and getattr(dept.head, "is_active", False)) else None
            if head:
                pool = [head]
            elif dept:
                pool = list(User.objects.filter(is_active=True, department=dept).exclude(id=u.id))
            else:
                pool = []
            if not pool:
                pool = list(User.objects.filter(is_active=True, is_superuser=True).exclude(id=u.id)[:1])
            moved["задачи"] = _rr_reassign(Task.objects.filter(assignee=u), "assignee", pool)
            moved["склад_задачи"] = _rr_reassign(WarehouseJob.objects.filter(assignee=u), "assignee", pool)
            moved["сделки"] = _rr_reassign(Deal.objects.filter(owner=u), "owner", pool)
            moved["лиды"] = _rr_reassign(Lead.objects.filter(owner=u), "owner", pool)
        u.apply_employment_status("dismissed")  # → is_active=False, is_superuser=False, dismissed_at=сьогодні
        targets = [p.get_full_name() or p.username for p in pool]
        try:
            from apps.crm.models import log_activity
            log_activity("contact", 0, "Звільнення співробітника",
                         "%s деактивовано, дані → %s" % (u.get_full_name() or u.username, ", ".join(targets) or "—"),
                         actor, "Адмін")
        except Exception:
            pass
        return Response({"ok": True, "is_sales": is_sales, "moved": {k: v for k, v in moved.items() if v},
                         "to": targets})
    required_perm = "roles.manage"


class MeView(APIView):
    """Текущий пользователь + его права (для фронта: какие пункты меню показывать)."""
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        # сотрудник может менять только свою тему оформления
        theme = request.data.get("theme")
        if theme is not None:
            request.user.theme = theme
            request.user.save(update_fields=["theme"])
        return Response(MeSerializer(request.user).data)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.prefetch_related("members", "funnels").all()
    serializer_class = DepartmentSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"


class InviteViewSet(viewsets.ModelViewSet):
    queryset = Invite.objects.select_related("department", "role").all()
    serializer_class = InviteSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"

    def perform_create(self, serializer):
        import secrets
        from django.utils import timezone
        from datetime import timedelta
        serializer.save(token=secrets.token_urlsafe(24), status="pending",
                        expires_at=timezone.now() + timedelta(days=7),
                        created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        inv = self.get_object(); inv.status = "revoked"; inv.save(update_fields=["status"])
        return Response({"ok": True})


class AcceptInviteView(APIView):
    """Публічна сторінка прийняття запрошення: інфо + встановлення пароля -> створення співробітника."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _get(self, token):
        from django.utils import timezone
        inv = Invite.objects.filter(token=token, status="pending").select_related("department").first()
        if not inv or inv.expires_at < timezone.now():
            return None
        return inv

    def get(self, request, token):
        inv = self._get(token)
        if not inv:
            return Response({"valid": False})
        return Response({"valid": True, "email": inv.email, "first_name": inv.first_name,
                         "last_name": inv.last_name, "department": inv.department.name if inv.department else ""})

    def post(self, request, token):
        inv = self._get(token)
        if not inv:
            return Response({"detail": "Запрошення недійсне або прострочене"}, status=status.HTTP_400_BAD_REQUEST)
        pwd = request.data.get("password") or ""
        if len(pwd) < 6:
            return Response({"detail": "Пароль мінімум 6 символів"}, status=status.HTTP_400_BAD_REQUEST)
        if inv.email and User.objects.filter(email__iexact=inv.email).exists():
            return Response({"detail": "Користувач з таким email вже існує"}, status=status.HTTP_400_BAD_REQUEST)
        base_un = (inv.email.split("@")[0] or "user").lower()
        un = base_un; i = 1
        while User.objects.filter(username=un).exists():
            i += 1; un = "%s%d" % (base_un, i)
        u = User.objects.create_user(username=un, email=inv.email, password=pwd,
                                     first_name=inv.first_name, last_name=inv.last_name,
                                     department=inv.department, role=inv.role)
        inv.status = "accepted"; inv.save(update_fields=["status"])
        return Response({"ok": True, "username": u.username}, status=status.HTTP_201_CREATED)


class PermissionsCatalogView(APIView):
    def get(self, request):
        from apps.accounts.models import PERMISSION_GROUPS
        groups = [{"group": g, "items": [{"code": c, "label": l, "hint": h} for c, l, h in items]} for g, items in PERMISSION_GROUPS]
        flat = [{"code": c, "label": l} for c, l in PERMISSION_CHOICES]
        return Response({"groups": groups, "flat": flat})
