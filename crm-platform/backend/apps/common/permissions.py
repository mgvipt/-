from rest_framework.permissions import BasePermission


class HasPermCode(BasePermission):
    """Проверяет код права из view.required_perm против роли пользователя."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        code = getattr(view, "required_perm", None)
        if code is None:
            return True
        return request.user.has_perm_code(code)
