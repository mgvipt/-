"""Import approved local Mio Gloss renders and build compact library previews."""

import io
import json
import re
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from apps.inbox.models import MediaLibraryItem, SharedLink


ROOMS = {
    "living": "living", "bedroom": "bedroom", "children": "kids", "kids": "kids",
    "corridor": "hallway", "hall": "hallway", "entrance": "hallway",
}


def image_webp(path, max_size, quality):
    """Return a compact WebP copy without altering the original source file."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, "WEBP", quality=quality, method=6)
    return output.getvalue()


def shared_file(filename, content):
    return SharedLink.objects.create(
        token=secrets.token_urlsafe(16), filename=filename, content_type="image/webp", data=content
    )


class Command(BaseCommand):
    help = "Import local Mio Gloss interiors and create WebP previews for the media library."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, help="Directory with colour subdirectories")
        parser.add_argument("--manifest", type=Path, help="Sand catalogue manifest.json")
        parser.add_argument("--rebuild-previews", action="store_true", help="Create missing previews for all existing image/catalog items")
        parser.add_argument("--dry-run", action="store_true")

    def _create_preview(self, item, dry_run):
        if item.preview_file_id or not item.file_id or not item.file.content_type.startswith("image/"):
            return False
        if dry_run:
            return True
        source = io.BytesIO(bytes(item.file.data))
        try:
            with Image.open(source) as original:
                image = original.convert("RGB")
                image.thumbnail((480, 270), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, "WEBP", quality=68, method=6)
        except (OSError, ValueError):
            return False
        item.preview_file = shared_file("preview-%s.webp" % item.file_id, output.getvalue())
        item.save(update_fields=["preview_file"])
        return True

    def handle(self, *args, **options):
        source = options.get("source")
        manifest = options.get("manifest")
        dry_run = options["dry_run"]
        imported = skipped = previews = 0

        if options["rebuild_previews"]:
            items = MediaLibraryItem.objects.filter(is_active=True, file__isnull=False, preview_file__isnull=True).select_related("file")
            for item in items.iterator():
                previews += int(self._create_preview(item, dry_run))

        if source:
            if not source.is_dir() or not manifest or not manifest.is_file():
                raise CommandError("--source and --manifest must point to existing paths")
            rows = json.loads(manifest.read_text())
            codes = {
                str(row["code"]).replace("/", "_").replace(",", "_"): row["code"]
                for row in rows
                if row.get("type") == "swatch" and row.get("code")
            }
            images = sorted(path for path in source.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
            for path in images:
                relative = path.relative_to(source).as_posix()
                directory = path.parent.name
                code = codes.get(directory)
                if not code:
                    self.stderr.write("Skipped unknown colour directory: %s" % relative)
                    skipped += 1
                    continue
                key = "source:%s" % relative
                if MediaLibraryItem.objects.filter(material="Песочки", tags__contains=key).exists():
                    skipped += 1
                    continue
                room = next((label for fragment, label in ROOMS.items() if fragment in path.stem.lower()), "showcase")
                version = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")[-58:]
                if dry_run:
                    imported += 1
                    continue
                full = image_webp(path, (1920, 1080), 84)
                preview = image_webp(path, (480, 270), 68)
                original = shared_file("mio-%s-%s.webp" % (code.replace("/", "-"), version), full)
                thumb = shared_file("preview-mio-%s-%s.webp" % (code.replace("/", "-"), version), preview)
                MediaLibraryItem.objects.create(
                    title="Mio Gloss · %s · %s" % (code, room), kind="image", section="colors",
                    material="Песочки", color_code=code,
                    tags="песочки інтер'єр effect:Mio Gloss room:%s revision:mio-approved-v2 %s" % (room, key),
                    file=original, preview_file=thumb,
                )
                imported += 1

        self.stdout.write(self.style.SUCCESS(
            "Mio import: imported=%s skipped=%s previews=%s dry_run=%s" % (imported, skipped, previews, dry_run)
        ))
