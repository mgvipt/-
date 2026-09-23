"""Private staff document references. Never included in shop or public library payloads."""
import os
import re
import stat
from pathlib import Path
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Product, InternalMaterialDocument


PRIVATE_DOCUMENT_ROOT = Path("/app/warehouse_photos/private_material_documents")


def private_document_path(sha):
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
        return None
    root = PRIVATE_DOCUMENT_ROOT.resolve()
    candidate = root / (sha + ".pdf")
    # Reject links even if their target is another file inside this folder.
    if candidate.is_symlink() or candidate.resolve().parent != root or not candidate.is_file():
        return None
    return candidate


def document_filename(doc):
    name = str(doc.original_filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()[:240]
    return name if name.lower().endswith(".pdf") else "document.pdf"


class CanReadMaterialDocuments(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.account_kind == "staff" and (
            user.is_superuser or user.has_perm_code("warehouse.view") or user.has_perm_code("inbox.view")
        ))


class ProductInternalDocuments(APIView):
    permission_classes = [IsAuthenticated, CanReadMaterialDocuments]
    http_method_names = ["get", "head", "options"]

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        ru = request.GET.get("lang") == "ru"
        items = []
        for doc in product.internal_documents.filter(is_active=True):
            # Validate legacy/imported rows again; never return a redirect target from an unchecked URL.
            try:
                key, url = InternalMaterialDocument.canonical_source(doc.source_url)
            except ValidationError:
                continue
            if key != doc.source_key:
                continue
            items.append({
                "id": doc.id, "title": (doc.title_ru or doc.title_uk) if ru else doc.title_uk,
                "translation_missing": ru and not bool(doc.title_ru), "kind": doc.kind,
                "document_number": doc.document_number, "original_language": doc.original_language,
                "issued_at": doc.issued_at, "valid_until": doc.valid_until,
                "is_archived": doc.is_archived, "notes": (doc.notes_ru or doc.notes_internal) if ru else doc.notes_internal,
                "notes_translation_missing": ru and bool(doc.notes_internal) and not bool(doc.notes_ru),
                "team_access_verified": doc.team_access_verified,
                "url": "" if private_document_path(doc.content_sha256) else url,
                "file_available": bool(private_document_path(doc.content_sha256)),
                "file_url": f"/api/products/{product.pk}/internal-documents/{doc.pk}/file/" if private_document_path(doc.content_sha256) else "",
            })
        response = Response({"items": items})
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class ProductInternalDocumentFile(APIView):
    permission_classes = [IsAuthenticated, CanReadMaterialDocuments]
    http_method_names = ["get", "head", "options"]

    def get(self, request, pk, docid):
        doc = get_object_or_404(InternalMaterialDocument, pk=docid, products__pk=pk, is_active=True)
        path = private_document_path(doc.content_sha256)
        if path is None:
            raise Http404
        try:
            # No database path is opened; the validated hash is the only file selector.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            stream = os.fdopen(fd, "rb")
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or stream.read(5) != b"%PDF-":
                stream.close()
                raise Http404
            stream.seek(0)
        except OSError:
            raise Http404
        response = FileResponse(stream, content_type="application/pdf", as_attachment=False, filename=document_filename(doc))
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "no-referrer"
        return response
