"""Публікація затвердженої бази знань у ChatPlace (Юля IG / TikTok). За замовчуванням — ПРОБНИЙ запуск.

    python manage.py kb_publish_chatplace --bot ig                     # різниця з живою базою ChatPlace (лише читання)
    python manage.py kb_publish_chatplace --bot ig --source crm-copy   # різниця зі знімком IG у CRM (ChatPlace не чіпаємо)
    python manage.py kb_publish_chatplace --bot ig --live --confirm N  # ЗАПИС — лише Олег, N = кількість змін з пробного запуску

Перед записом зберігається бекап поточної бази ChatPlace у JSON. Нічого не видаляється.
"""
import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge.publisher import BOTS, apply, fetch_crm_copy, fetch_remote, plan, rules_count


class Command(BaseCommand):
    help = "Затверджена база знань → база Q&A Юлі в ChatPlace (IG / TikTok). Без --live нічого не пише."

    def add_arguments(self, p):
        p.add_argument("--bot", choices=sorted(BOTS), required=True)
        p.add_argument("--source", choices=["live", "crm-copy"], default="live")
        p.add_argument("--live", action="store_true")
        p.add_argument("--confirm", type=int, default=-1, help="Кількість змін (додати+оновити) з пробного запуску")
        p.add_argument("--backup-dir", default="/tmp")
        p.add_argument("--show", type=int, default=15)

    def handle(self, *a, **o):
        bot, w = o["bot"], self.stdout.write
        if o["live"] and o["source"] != "live":
            raise CommandError("Запис можливий лише проти живої бази ChatPlace (--source live)")
        remote = fetch_remote(bot) if o["source"] == "live" else fetch_crm_copy()
        if o["source"] == "crm-copy" and bot != "ig":
            w("⚠️ Знімок у CRM — це база Instagram. Справжню різницю з TikTok покаже лише --source live.")
        ops = plan(bot, remote)
        add = [x for x in ops if x["op"] == "add"]
        upd = [x for x in ops if x["op"] == "update"]
        same = [x for x in ops if x["op"] == "same"]
        w("ПУБЛІКАЦІЯ → %s [%s], порівняння з: %s (%d записів)" % (
            BOTS[bot]["label"], "ЗАПИС" if o["live"] else "ПРОБНИЙ ЗАПУСК", o["source"], len(remote)))
        w("Затверджено для публікації: %d · без змін: %d · оновити: %d · додати: %d" % (len(ops), len(same), len(upd), len(add)))
        w("Правила (тип «Правило») у глобальні правила ChatPlace на цьому етапі НЕ публікуються: %d" % rules_count(bot))
        for x in upd[:o["show"]]:
            w("~ #%d «%s»\n    БУЛО:  %s\n    СТАНЕ: %s" % (x["item"].id, x["question"][:80], x["old"][:220].replace("\n", " "),
                                                        x["new"][:220].replace("\n", " ")))
        for x in add[:o["show"]]:
            w("+ #%d «%s»: %s" % (x["item"].id, x["question"][:80], x["new"][:200].replace("\n", " ")))
        changes = len(add) + len(upd)
        if not o["live"]:
            w("Щоб записати (лише Олег): --live --confirm %d" % changes)
            return
        if o["confirm"] != changes:
            raise CommandError("Кількість змін зараз %d, а --confirm %d. Спершу подивіться пробний запуск." % (changes, o["confirm"]))
        if not changes:
            w("Змін немає.")
            return
        path = os.path.join(o["backup_dir"], "kb_publish_backup_%s_%s.json" % (bot, datetime.now().strftime("%Y%m%d_%H%M%S")))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(remote, f, ensure_ascii=False)
        w("Бекап поточної бази ChatPlace: %s" % path)
        done = apply(bot, [x for x in ops if x["op"] != "same"] + same)
        w("Готово: додано %d, оновлено %d, помилок %d" % (done["add"], done["update"], len(done["errors"])))
        for e in done["errors"]:
            w("  ! " + e)
