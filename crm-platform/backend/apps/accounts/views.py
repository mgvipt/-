from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import User, Role
from .serializers import UserSerializer, RoleSerializer, MeSerializer
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
