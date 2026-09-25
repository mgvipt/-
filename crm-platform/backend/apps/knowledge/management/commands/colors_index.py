# -*- coding: utf-8 -*-
"""Порахувати середній колір кожного нашого образка з бібліотеки (для підбору за RAL/NCS)."""
import io

from django.core.management.base import BaseCommand
from PIL import Image

from apps.inbox.models import MediaLibraryItem
from apps.knowledge.colors import rgb_to_hex, rgb_to_lab
from apps.knowledge.models import SwatchColor

SWATCH_WORDS = ("зразок", "каталог", "sample")


def average_rgb(data):
    """Середній колір центральної частини образка — краї часто містять рамку, підпис або тінь."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    box = (int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75))
    im = im.crop(box).resize((24, 24), Image.Resampling.LANCZOS)
    px = list(im.getdata())
    n = len(px)
    return tuple(sum(p[i] for p in px) / n for i in range(3))


class Command(BaseCommand):
    help = "Перерахувати колір образків бібліотеки"

    def handle(self, *args, **opts):
        done = skip = 0
        qs = (MediaLibraryItem.objects.filter(section="colors", is_active=True)
              .exclude(color_code="").select_related("preview_file", "file"))
        for item in qs:
            title = ((item.title or "") + " " + (item.tags or "")).lower()
            if not any(w in title for w in SWATCH_WORDS):
                continue
            src = item.preview_file or item.file
            if not src or not src.data:
                skip += 1
                continue
            try:
                rgb = average_rgb(src.data)
            except Exception:
                skip += 1
                continue
            lab = rgb_to_lab(rgb)
            SwatchColor.objects.update_or_create(
                item_id=item.id,
                defaults=dict(material=item.material or "", color_code=item.color_code,
                              hex=rgb_to_hex(rgb), lab_l=lab[0], lab_a=lab[1], lab_b=lab[2]))
            done += 1
        self.stdout.write("образків порахано: %d, пропущено: %d, у базі: %d"
                          % (done, skip, SwatchColor.objects.count()))
