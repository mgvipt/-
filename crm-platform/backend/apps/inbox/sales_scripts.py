"""One canonical, read-only staff playbook source; no QuickReply duplication."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

SOURCE = Path(__file__).with_name("data") / "selected-sales-scripts.json"

@lru_cache(maxsize=1)
def script_library():
    raw = SOURCE.read_bytes()
    data = json.loads(raw)
    # Provenance and import/editorial notes stay out of the UI payload.
    return {"version": hashlib.sha256(raw).hexdigest(), "default_language": "uk",
            "groups": data["groups"], "shared_nodes": data["shared_nodes"],
            "scripts": [{k: s[k] for k in ("id", "group", "title", "steps", "product_refs")} for s in data["scripts"]]}

class CanReadSalesScripts(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.account_kind == "staff" and
                    (user.is_superuser or user.has_perm_code("inbox.view")))

class SalesScripts(APIView):
    permission_classes = [IsAuthenticated, CanReadSalesScripts]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        response = Response(script_library())
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
