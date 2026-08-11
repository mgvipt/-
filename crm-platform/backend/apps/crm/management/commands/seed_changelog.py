# -*- coding: utf-8 -*-
"""Заповнює історію змін CRM (сторінка «Що нового») двомовними записами (uk/ru).
Дані — у сусідньому changelog_seed.json (експорт з БД). Ідемпотентно: upsert за (дата+title_uk).
Запуск: python manage.py seed_changelog"""
import json
import os
from django.core.management.base import BaseCommand
from apps.crm.models import ChangeLogEntry

SEED = os.path.join(os.path.dirname(__file__), "changelog_seed.json")


class Command(BaseCommand):
    help = "Seed CRM changelog (сторінка «Що нового») — двомовно uk/ru"

    def handle(self, *args, **opts):
        try:
            entries = json.load(open(SEED, encoding="utf-8"))
        except Exception as e:
            self.stderr.write("changelog seed json не прочитано: %s" % e)
            return
        added = 0
        for r in entries:
            key = r.get("section_key") or "general"
            title_uk = r.get("title_uk") or r.get("title") or ""
            title_ru = r.get("title_ru") or title_uk
            body_uk = r.get("body_uk") or r.get("body") or ""
            body_ru = r.get("body_ru") or body_uk
            defaults = dict(section=key, section_key=key,
                            title=title_uk[:200], body=body_uk,
                            title_uk=title_uk[:200], title_ru=title_ru[:200],
                            body_uk=body_uk, body_ru=body_ru)
            obj, created = ChangeLogEntry.objects.get_or_create(
                d=r["d"], title_uk=title_uk[:200], defaults=defaults)
            if created:
                added += 1
            else:
                changed = []
                for f, v in defaults.items():
                    if getattr(obj, f) != v:
                        setattr(obj, f, v); changed.append(f)
                if changed:
                    obj.save(update_fields=changed)
        self.stdout.write("changelog: додано %d, всього %d" % (added, ChangeLogEntry.objects.count()))
