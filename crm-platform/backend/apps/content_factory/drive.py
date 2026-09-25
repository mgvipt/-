"""Контент-завод: Google Drive як джерело (24.09.2026). Файли НЕ копіюються — лише id, назва, шлях папок, посилання.
Доступ: той самий сервісний акаунт, що й GA4 (GA4_SA_KEY_B64, ads-bot@ads-analytics-492919), scope drive.readonly.
Матеріал визначається за назвами папок у шляху («ВЕЛЬВЕТ Луна / Баранюк» → Вельвет Луна).
Файл завантажується з Drive лише коли йде в пост (download) — до 45 МБ, більші пропускаються.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from django.utils import timezone

from .models import DriveFolder, SourceAsset
from .sources import tags_from_caption

API = "https://www.googleapis.com/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_DEPTH = 6
MAX_FILES_PER_FOLDER = 20000
MAX_DOWNLOAD = 45 * 1024 * 1024
_token = {"value": "", "exp": 0}


class DriveError(Exception):
    pass


def configured():
    return bool(os.environ.get("GA4_SA_KEY_B64"))


def _b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def token():
    if _token["value"] and _token["exp"] > time.time() + 60:
        return _token["value"]
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    if not configured():
        raise DriveError("Немає ключа сервісного акаунта Google (GA4_SA_KEY_B64).")
    key = json.loads(base64.b64decode(os.environ["GA4_SA_KEY_B64"]))
    now = int(time.time())
    signing_input = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + b"." + _b64u(json.dumps({
        "iss": key["client_email"], "scope": SCOPE, "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600}).encode())
    pk = serialization.load_pem_private_key(key["private_key"].encode(), password=None)
    assertion = signing_input + b"." + _b64u(pk.sign(signing_input, padding.PKCS1v15(), hashes.SHA256()))
    data = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                   "assertion": assertion.decode()}).encode()
    resp = json.load(urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data),
                                            timeout=30))
    _token.update(value=resp["access_token"], exp=time.time() + int(resp.get("expires_in", 3600)))
    return _token["value"]


def service_email():
    if not configured():
        return ""
    return json.loads(base64.b64decode(os.environ["GA4_SA_KEY_B64"])).get("client_email", "")


def _get(url, raw=False):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read() if raw else json.load(r)
    except urllib.error.HTTPError as e:
        raise DriveError(f"Google Drive HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise DriveError(f"Google Drive недоступний: {e}") from None


def folder_meta(folder_id):
    return _get(f"{API}/{folder_id}?fields=id,name,mimeType&supportsAllDrives=true")


def children(folder_id):
    page = ""
    fields = "nextPageToken,files(id,name,mimeType,size,webViewLink,createdTime,imageMediaMetadata(width,height),videoMediaMetadata(width,height,durationMillis))"
    while True:
        q = urllib.parse.quote(f"'{folder_id}' in parents and trashed = false")
        r = _get(f"{API}?q={q}&pageSize=1000&fields={fields}&supportsAllDrives=true&includeItemsFromAllDrives=true"
                 + (f"&pageToken={page}" if page else ""))
        yield from r.get("files", [])
        page = r.get("nextPageToken")
        if not page:
            return


def sync_folder(folder):
    """Обійти папку (до 6 рівнів) і занести фото/відео в SourceAsset. Повертає кількість файлів."""
    count = 0
    stack = [(folder.folder_id, [folder.title or ""])]
    while stack and count < MAX_FILES_PER_FOLDER:
        fid, path = stack.pop()
        for f in children(fid):
            mime = f.get("mimeType", "")
            if mime == FOLDER_MIME:
                if len(path) < MAX_DEPTH:
                    stack.append((f["id"], path + [f["name"]]))
                continue
            kind = "photo" if mime.startswith("image/") else "video" if mime.startswith("video/") else ""
            if not kind:
                continue
            place = " / ".join(p for p in path if p)
            material, tags = tags_from_caption(place + " " + f.get("name", ""))
            meta = f.get("imageMediaMetadata") or f.get("videoMediaMetadata") or {}
            SourceAsset.objects.update_or_create(file_unique_id="drive:" + f["id"], defaults={
                "origin": SourceAsset.Origin.DRIVE, "kind": kind, "file_id": f["id"], "mime": mime, "blog_id": folder.blog_id,
                "size": int(f["size"]) if f.get("size") else None, "width": meta.get("width"), "height": meta.get("height"),
                "duration": int(meta["durationMillis"]) // 1000 if meta.get("durationMillis") else None,
                "file_name": f.get("name", "")[:255], "caption": place, "link": f.get("webViewLink", ""),
                "material": material, "tags": tags, "posted_at": f.get("createdTime"),
            })
            count += 1
    return count


def sync_all():
    done = {}
    for folder in DriveFolder.objects.filter(enabled=True):
        try:
            if not folder.title:
                folder.title = folder_meta(folder.folder_id).get("name", "")[:200]
            folder.files_count = sync_folder(folder)
            folder.last_error = ""
        except DriveError as e:
            folder.last_error = str(e)[:300]
        folder.last_sync_at = timezone.now()
        folder.save()
        done[folder.title or folder.folder_id] = folder.last_error or folder.files_count
    return done


def thumbnail(file_id):
    meta = _get(f"{API}/{file_id}?fields=thumbnailLink&supportsAllDrives=true")
    link = meta.get("thumbnailLink")
    if not link:
        return None
    return _get(link.replace("=s220", "=s400"), raw=True), "image/jpeg"


def download(asset):
    if asset.size and asset.size > MAX_DOWNLOAD:
        raise DriveError(f"Файл «{asset.file_name}» більший за 45 МБ — Telegram його не прийме.")
    return _get(f"{API}/{asset.file_id}?alt=media&supportsAllDrives=true", raw=True)


def parse_folder_link(text):
    """https://drive.google.com/drive/folders/<id>?… або просто id → id."""
    t = (text or "").strip()
    if "/folders/" in t:
        t = t.split("/folders/")[1]
    return t.split("?")[0].split("/")[0].strip()
