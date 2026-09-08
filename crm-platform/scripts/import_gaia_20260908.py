"""Add approved Gaia interiors only. MODE=DRY_RUN (default), TEST (2), LIVE."""
import hashlib
import json
import os
import secrets
from pathlib import Path
from django.db import connection, transaction
from apps.inbox.models import MediaLibraryItem, SharedLink

ROOT=Path(os.environ.get("GAIA_SOURCE","/tmp/gaia-release-20260908"))
BATCH="gaia-real-20260908"
MODE=os.environ.get("MODE","DRY_RUN")
ROOMS={"living":"Вітальня","bedroom":"Спальня","children":"Дитяча","hallway":"Передпокій"}

def main():
    if MODE not in {"DRY_RUN","TEST","LIVE"}:
        raise RuntimeError("Invalid mode")
    manifest=json.loads((ROOT/"manifest.json").read_text())
    rows=manifest["images"]
    if len(rows)!=192 or len({(r["code"],r["room"]) for r in rows})!=192:
        raise RuntimeError("Invalid manifest")
    colors={r["code"] for r in rows}
    catalog=set(MediaLibraryItem.objects.filter(is_active=True,material="Песочки",tags__icontains="каталог зразок").values_list("color_code",flat=True))
    if colors!=catalog or len(colors)!=48:
        raise RuntimeError("Catalog mismatch")
    for color in colors:
        if {r["room"] for r in rows if r["code"]==color}!=set(ROOMS):
            raise RuntimeError("Incomplete rooms")
    for r in rows:
        for folder,key in [("images","sha256"),("previews","preview_sha256")]:
            b=(ROOT/folder/r["filename"]).read_bytes()
            if hashlib.sha256(b).hexdigest()!=r[key]:
                raise RuntimeError("Hash mismatch "+r["filename"])
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)",[202609081])
        existing=set(MediaLibraryItem.objects.filter(tags__contains=BATCH).values_list("file__filename",flat=True))
        pending=[r for r in rows if r["filename"] not in existing]
        print(json.dumps({"mode":MODE,"expected":192,"existing":len(existing),"would_create":len(pending),"new_shared_links":len(pending)*2,"colors":48,"old_records_affected":0},ensure_ascii=False))
        if MODE=="DRY_RUN":
            return
        selected=pending[:2] if MODE=="TEST" else pending
        created=[]
        for r in selected:
            full=SharedLink.objects.create(token=secrets.token_urlsafe(32),filename=r["filename"],content_type="image/webp",data=(ROOT/"images"/r["filename"]).read_bytes())
            thumb=SharedLink.objects.create(token=secrets.token_urlsafe(32),filename="preview-"+r["filename"],content_type="image/webp",data=(ROOT/"previews"/r["filename"]).read_bytes())
            item=MediaLibraryItem.objects.create(
                title=f"Gaia Gloss · {ROOMS[r['room']]} · тепле / холодне світло",
                kind="image",section="colors",material="Песочки",color_code=r["code"],
                tags=f"песочки інтер'єр, effect:Gaia Gloss, room:{r['room']}, AI візуалізація, revision:{BATCH}",
                file=full,preview_file=thumb,public_url=f"https://crm.wallcovdec.com.ua/api/f/{full.token}/",
                sort=800+rows.index(r))
            created.append({"id":item.id,"file_id":full.id,"preview_file_id":thumb.id,"code":r["code"],"room":r["room"],"url":item.public_url,"sha256":r["sha256"]})
    print(json.dumps({"created":len(created),"items":created},ensure_ascii=False))

if __name__=="__main__":
    main()
