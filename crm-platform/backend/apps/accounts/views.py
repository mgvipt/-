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


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("role", "department").order_by("username")
    serializer_class = UserSerializer
    permission_classes = [HasPermCode]
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
