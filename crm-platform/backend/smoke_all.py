# -*- coding: utf-8 -*-
"""Смоук-перевірка ключових функцій CRM перед деплоєм.

Запускається у deploy.sh НА НОВОМУ образі ДО `up -d`: якщо хоч одна перевірка
червона — деплой зупиняється, стара версія продовжує працювати.

Тільки читання (GET), без жодного запису. Дві ролі:
  owner   — суперюзер (усі екрани, включно з фінансами й маркетингом)
  manager — Ілона (id=2): робочі екрани менеджера, перевірка прав

Додаєш нову видиму функцію → додай сюди рядок CHECKS. Правило для Claude і Codex.
"""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

HOST = "crm.wallcovdec.com.ua"

# (назва, роль, url, допустимі статуси, обов'язкові ключі верхнього рівня)
CHECKS = [
    # ── базове ──
    ("Мій профіль (owner)", "owner", "/api/me/", {200}, []),
    ("Мій профіль (менеджер)", "manager", "/api/me/", {200}, []),
    ("Глобальний пошук", "owner", "/api/search/?q=test", {200}, []),
    # ── CRM: угоди / контакти / задачі ──
    ("Список угод", "owner", "/api/deals/?page_size=5", {200}, []),
    ("Картка угоди (остання)", "owner", "DEAL_DETAIL", {200}, []),
    ("Список угод (менеджер)", "manager", "/api/deals/?page_size=5", {200}, []),
    ("Список контактів", "owner", "/api/contacts/?page_size=5", {200}, []),
    ("Картка контакту (останній)", "owner", "CONTACT_DETAIL", {200}, []),
    ("Задачі", "owner", "/api/tasks/?page_size=5", {200}, []),
    ("Дублікати", "owner", "/api/duplicates/", {200}, []),
    ("Дублікати: номер переписки", "owner", "/api/duplicates/?by=chat", {200}, []),
    ("Дублікати: месенджер", "owner", "/api/duplicates/?by=social", {200}, []),
    # ── Чати / відкриті лінії ──
    ("Список чатів", "owner", "/api/conversations/?page_size=5", {200}, []),
    ("Список чатів (менеджер)", "manager", "/api/conversations/?page_size=5", {200}, []),
    ("Інбокс-пінг", "owner", "/api/inbox/ping/", {200}, []),
    ("Контакт-центр", "owner", "/api/contact-center/", {200}, []),
    # ── Гроші (найдорожче) ──
    ("Журнал операцій", "owner", "/api/transactions/?page_size=5", {200}, []),
    ("Оплати", "owner", "/api/payments/?page_size=5", {200}, []),
    ("Фінанси: дашборд", "owner", "/api/finance/dashboard/", {200}, []),
    ("Фінанси: огляд", "owner", "/api/finance/overview/", {200}, []),
    ("Фінанси: P&L", "owner", "/api/finance/pnl/", {200}, []),
    ("Фінанси: рахунки", "owner", "/api/accounts/", {200}, []),
    ("КПІ менеджерів", "owner", "/api/finance/salary/", {200}, []),
    ("КПІ: свої цифри (менеджер)", "manager", "/api/finance/salary/", {200, 403}, []),
    # ── Аналітика й маркетинг ──
    ("Аналітика продажів", "owner", "/api/analytics/", {200}, []),
    ("Маркетинг: основний звіт", "owner", "/api/meta-marketing/", {200}, ["sections"]),
    ("Маркетинг: GA4 + заявки сайтів", "owner", "/api/marketing/ga4/", {200}, ["sites", "crm_leads"]),
    ("Маркетинг: офлайн-воронки", "owner", "/api/marketing/offline/", {200}, []),
    ("Маркетинг: піксель", "owner", "/api/meta-marketing/pixel-events/", {200}, []),
    ("Маркетинг закритий менеджеру без прав", "manager", "/api/meta-marketing/", {200, 403}, []),
    # ── Склад ──
    ("Склад: товари", "owner", "/api/products/?page_size=5", {200}, []),
    ("Склад: дашборд", "owner", "/api/warehouse/dashboard/", {200}, []),
    ("Склад: черга робіт", "owner", "/api/warehouse/queue/", {200}, []),
    ("Склад: інвентаризаційна відомість", "owner",
     "/api/warehouse/inventory-sheet/?from=2026-07-31&to=2026-09-02&page_size=5", {200}, ["rows"]),
    # ── Персонал ──
    ("Аналітика співробітників", "owner", "/api/staff/analytics/", {200}, []),
    ("Що нового", "owner", "/api/changelog/", {200}, []),
    # мініатюри фото в чатах: без підпису має бути 403 (маршрут живий, перебір закритий)
    ("Мініатюри фото в чаті", "owner", "/api/inbox/thumb/1/0/", {403}, []),
]


def resolve_dynamic(url):
    from apps.crm.models import Contact, Deal
    if url == "DEAL_DETAIL":
        deal = Deal.objects.order_by("-id").first()
        return "/api/deals/%s/" % deal.pk if deal else None
    if url == "CONTACT_DETAIL":
        contact = Contact.objects.order_by("-id").first()
        return "/api/contacts/%s/" % contact.pk if contact else None
    return url


def main():
    User = get_user_model()
    owner = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
    manager = User.objects.filter(pk=2, is_active=True).first()
    if owner is None:
        print("FATAL: немає активного суперюзера")
        return 1

    clients = {"owner": APIClient()}
    clients["owner"].force_authenticate(owner)
    if manager is not None:
        clients["manager"] = APIClient()
        clients["manager"].force_authenticate(manager)

    failed = []
    skipped = 0
    for name, role, url, ok_statuses, need_keys in CHECKS:
        client = clients.get(role)
        if client is None:
            skipped += 1
            print("SKIP  %-42s (немає користувача ролі %s)" % (name, role))
            continue
        real_url = resolve_dynamic(url)
        if real_url is None:
            skipped += 1
            print("SKIP  %-42s (немає даних)" % name)
            continue
        try:
            r = client.get(real_url, HTTP_HOST=HOST)
            status = r.status_code
            problem = None
            if status not in ok_statuses:
                problem = "HTTP %s" % status
            elif status == 200 and need_keys:
                try:
                    body = r.json()
                except Exception:
                    body = None
                if not isinstance(body, dict):
                    problem = "відповідь не JSON-обʼєкт"
                else:
                    missing = [k for k in need_keys if k not in body]
                    if missing:
                        problem = "немає ключів: %s" % ", ".join(missing)
        except Exception as exc:  # 500 всередині теж прилетить сюди або статусом
            problem = "%s: %s" % (type(exc).__name__, exc)
        if problem:
            failed.append((name, real_url, problem))
            print("FAIL  %-42s %s — %s" % (name, real_url, problem))
        else:
            print("ok    %-42s" % name)

    print("-" * 60)
    total = len(CHECKS)
    if failed:
        print("СМОУК ПРОВАЛЕНО: %s з %s перевірок червоні. Деплой зупинено." % (len(failed), total))
        for name, real_url, problem in failed:
            print("  • %s (%s): %s" % (name, real_url, problem))
        return 1
    print("СМОУК OK: %s перевірок зелені (%s пропущено)." % (total - skipped, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
