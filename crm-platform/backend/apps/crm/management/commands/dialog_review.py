# -*- coding: utf-8 -*-
"""Нічний розбір діалогів (5:00) і тижневий аудит (понеділок). Олег, 26.09.2026."""
from datetime import datetime

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Розбір вчорашніх діалогів (--daily) або тижневий аудит (--weekly)"

    def add_arguments(self, p):
        p.add_argument("--weekly", action="store_true", help="тижневий аудит замість денного")
        p.add_argument("--day", default="", help="конкретний день YYYY-MM-DD (за замовчуванням — вчора)")
        p.add_argument("--no-tg", action="store_true", help="не надсилати звіт у Telegram")
        p.add_argument("--no-ai", action="store_true", help="тільки формальні перевірки, без ШІ")
        p.add_argument("--days", type=int, default=1, help="скільки днів назад аналізувати")

    def handle(self, *a, **o):
        from apps.crm import dialog_review as dr
        if o["weekly"]:
            rev = dr.run_weekly(send_tg=not o["no_tg"])
        else:
            day = datetime.strptime(o["day"], "%Y-%m-%d").date() if o["day"] else None
            rev = dr.run_daily(day=day, send_tg=not o["no_tg"], ai=not o["no_ai"], days=o.get("days") or 1)
        self.stdout.write("Розбір #%s (%s %s): зауважень %s, правил %s, $%s"
                          % (rev.id, rev.kind, rev.period_start, len(rev.issues or []),
                             len(rev.proposals or []), rev.cost_usd))
