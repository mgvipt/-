"""Authentication boundary between client accounts and the internal CRM."""

from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import PermissionDenied


CLIENT_SAFE_API_PATHS = frozenset({
    "/api/me/",
    "/api/auth/register/",
    "/api/auth/token/",
    "/api/pricelist/",
    "/api/zamer/projects/",
    "/api/zamer/register/",
    "/api/zamer/reviews/",
    "/api/zamer/self-estimate/",
})


def _normalized_path(request) -> str:
    path = str(getattr(request, "path_info", "") or "/")
    return path.rstrip("/") + "/"


def enforce_client_api_boundary(request, user) -> None:
    """Reject every internal CRM API for an authenticated client account.

    This check lives in authentication rather than individual permissions, so
    a view that explicitly declares ``IsAuthenticated`` cannot bypass it.
    Public webhook views with ``authentication_classes = []`` keep their
    existing anonymous contract and receive no authenticated client identity.
    """

    if getattr(user, "account_kind", "staff") != "client":
        return
    if _normalized_path(request) not in CLIENT_SAFE_API_PATHS:
        raise PermissionDenied("Клиентскому аккаунту недоступен внутренний раздел CRM")


class ClientScopedSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            enforce_client_api_boundary(request, result[0])
        return result


class ClientScopedTokenAuthentication(TokenAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            enforce_client_api_boundary(request, result[0])
        return result
