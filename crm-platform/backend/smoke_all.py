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
    ("Товари: джерело ШІ потребує окремого ключа", "manager", "/api/product-source/", {403}, []),
    ("Товари: характеристики та спільна бібліотека", "manager", "/api/products/1653/facts/", {200}, ["shop_specs", "media", "price"]),
    ("Шовк: бібліотека кольорів", "manager", "/api/inbox/media-library/?view=picker&material=%D0%9C%D0%BE%D0%BA%D1%80%D0%B8%D0%B9%20%D1%88%D0%BE%D0%B2%D0%BA", {200}, ["items"]),
    ("Бібліотека: захист коротких посилань", "manager", "/api/l/not-valid", {404}, []),
    ("Cezar: бібліотека моделей", "manager", "/api/inbox/media-library/?view=picker&material=%D0%9F%D0%BB%D1%96%D0%BD%D1%82%D1%83%D1%81%D0%B8%20Cezar", {200}, ["items"]),
    # 16.09.2026 (Олег): тест-набори — вага з комплектації, фіксовані ставки за тонування набору
    ("Склад: ставки (тест-набір, тонування набору)", "owner", "/api/warehouse/my-salary/", {200}, ["rates"]),
    # 16.09.2026 (Олег): звіт власника — кожне відвантаження з фото накладної/коробки/архіву тонування
    ("Склад: звіт відвантажень з фото", "owner", "/api/warehouse/dashboard/?period=week", {200}, ["rows", "shipments"]),
    ("Склад: мите відро", "owner", "/api/warehouse/washed/", {200}, ["pairs"]),
    ("Розвиток: подяки від керівника", "manager", "/api/gamification/thanks/?user=me", {200}, ["items"]),
    ("Склад: викраски з А3", "owner", "/api/warehouse/samples/", {200}, ["recipes"]),
    # 17.09.2026 (Олег): вкладка «Всі співробітники» / забрати чужий чат — окремі права; «взяв» без повторів
    ("Права: каталог (Всі співробітники, чужий чат)", "owner", "/api/permissions/", {200}, ["groups"]),
    ("Відкриті лінії: фільтр співробітника (менеджер)", "manager", "/api/conversations/?page_size=5&manager=3", {200}, ["results"]),
    ("Аналітика: дії менеджерів (взяв без повторів)", "owner", "/api/analytics/manager-actions/", {200}, []),
    ("Інвентаризація: колонка повернень", "owner", "/api/warehouse/inventory-sheet/?page_size=5", {200}, ["rows"]),
    # ── базове ──
    ("Мій профіль (owner)", "owner", "/api/me/", {200}, []),
    ("Мій профіль (менеджер)", "manager", "/api/me/", {200}, []),
    ("Глобальний пошук", "owner", "/api/search/?q=test", {200}, []),
    ("Глобальний пошук: 2 слова + група чатів", "owner", "/api/search/?q=%D0%A2%D0%B5%D1%81%D1%82%20%D0%9A%D0%BB%D1%96%D1%94%D0%BD%D1%82", {200}, ["clients", "chats", "deals", "leads"]),
    ("Пошук у чатах: 2 слова (менеджер)", "manager", "/api/conversations/?page_size=5&search=%D0%A2%D0%B5%D1%81%D1%82%20%D0%9A%D0%BB%D1%96%D1%94%D0%BD%D1%82", {200}, ["results"]),
    # ── CRM: угоди / контакти / задачі ──
    ("Список угод", "owner", "/api/deals/?page_size=5", {200}, []),
    ("Картка угоди (остання)", "owner", "DEAL_DETAIL", {200}, []),
    ("Список угод (менеджер)", "manager", "/api/deals/?page_size=5", {200}, []),
    ("Список контактів", "owner", "/api/contacts/?page_size=5", {200}, []),
    ("Картка контакту (останній)", "owner", "CONTACT_DETAIL", {200}, []),
    ("Якість звернення (контакт)", "owner", "CONTACT_LEAD_QUALITY", {200}, ["lead_id", "choices"]),
    ("Задачі", "owner", "/api/tasks/?page_size=5", {200}, []),
    ("Дублікати", "owner", "/api/duplicates/", {200}, []),
    ("Дублікати: номер переписки", "owner", "/api/duplicates/?by=chat", {200}, []),
    ("Дублікати: месенджер", "owner", "/api/duplicates/?by=social", {200}, []),
    # ── Чати / відкриті лінії ──
    ("Список чатів", "owner", "/api/conversations/?page_size=5", {200}, []),
    ("Список чатів (менеджер)", "manager", "/api/conversations/?page_size=5", {200}, []),
    ("Лендинг: менеджер бачить угоди воронки 22", "manager", "/api/deals/?funnel=22&page_size=5", {200}, []),
    ("Лендинг: менеджер бачить чати каналу web", "manager", "/api/conversations/?channel=10&page_size=5", {200}, []),
    ("Чат-коментар: куди піде відповідь", "owner", "/api/conversations/6555/comment_target/", {200}, ["is_comment", "target"]),
    ("Лендинг dekoratyvna: менеджер бачить угоди воронки", "manager", "FUNNEL_DEALS:Лендинг · dekoratyvna-shtukaturka.com.ua", {200}, []),
    ("Заявки магазину: маршрут живий (лише підписаний POST)", "owner", "/api/integrations/shop/leads/", {405}, []),
    # ── Відгуки покупців ──
    ("Відгуки: на перевірці (власник)", "owner", "/api/reviews/?status=pending", {200}, ["results", "counts"]),
    ("Відгуки: журнал просьб (відправка вимкнена)", "owner", "/api/reviews/requests/", {200}, ["results", "send_enabled"]),
    ("Відгуки: правила", "owner", "/api/reviews/settings/", {200}, ["send_enabled", "google_review_url"]),
    ("Відгуки: менеджер без права — закрито", "manager", "/api/reviews/", {200, 403}, []),
    ("Відгуки магазину: маршрут живий (лише підписаний POST)", "owner", "/api/integrations/shop/reviews/invite/", {405}, []),
    ("Відгуки: фото без підпису закрите", "owner", "/api/reviews/photo/not-a-token/", {404}, []),
    ("Відгуки: тексти, історія, тестовий режим", "owner", "/api/reviews/settings/", {200}, ["text_versions", "test_mode", "allowlist_contacts"]),
    ("Відгуки: «не просити» у картці клієнта", "manager", "CONTACT_REVIEW_OPTOUT", {200}, ["opt_out", "can_remove"]),
    ("Інбокс-пінг", "owner", "/api/inbox/ping/", {200}, []),
    ("Контакт-центр", "owner", "/api/contact-center/", {200}, []),
    # ── Гроші (найдорожче) ──
    ("Журнал операцій", "owner", "/api/transactions/?page_size=5", {200}, []),
    ("Оплати", "owner", "/api/payments/?page_size=5", {200}, []),
    ("Фінанси: дашборд", "owner", "/api/finance/dashboard/", {200}, []),
    ("Фінанси: огляд", "owner", "/api/finance/overview/", {200}, []),
    ("Фінанси: P&L", "owner", "/api/finance/pnl/", {200}, []),
    ("Фінанси: знімки дня", "owner", "/api/day-snapshots/", {200}, ["results", "can_close_day"]),
    ("Фінанси: знімки дня (менеджер з журналом)", "manager", "/api/day-snapshots/", {200}, ["results"]),
    ("Фінанси: залишки для «Закрити день» (обовʼязкові рахунки)", "owner", "/api/day-snapshots/balances/", {200}, ["accounts"]),
    ("Маржа угоди: картка угоди менеджера — margin є (null без права deal.margin.view), бонус є", "manager", "DEAL_DETAIL", {200}, ["margin", "bonus"]),
    ("Економіка угоди: матеріали пакування — % фонду «Упаковка (матеріали)» з Фінмоделі", "owner", "/api/deal-economics/settings/", {200}, ["pack_material_fund_pct", "pack_material_fund_name"]),
    ("База знань ІІ: тестовий чат — агенти", "owner", "/api/knowledge/test-chat/", {200}, ["agents", "can_test"]),
    ("База знань ІІ: попередня перевірка чернеток — підсумок", "owner", "/api/knowledge/precheck/", {200}, ["labels", "counts", "runs"]),
    ("База знань ІІ: контролер — лише за запуском", "owner", "/api/knowledge/controller/", {200}, ["periods", "scheduled", "runs"]),
    ("База знань ІІ: веб-чат ІІ (вимкнено за замовчуванням)", "owner", "/api/knowledge/settings/", {200}, ["webchat_ai_enabled", "webchat_items"]),
    ("База знань ІІ: тестовий чат — менеджер (доступ або закрито)", "manager", "/api/knowledge/test-chat/", {200, 403}, []),
    ("База знань ІІ: записи (власник)", "owner", "/api/knowledge/items/?page_size=5", {200}, ["results", "count"]),
    ("База знань ІІ: довідник і права", "owner", "/api/knowledge/meta/", {200}, ["topics", "audiences", "can_approve", "roles"]),
    ("База знань ІІ: що бачить AI-РОП", "owner", "/api/knowledge/preview/?agent=rop_hint&q=%D0%B4%D0%BE%D1%81%D1%82%D0%B0%D0%B2%D0%BA%D0%B0", {200}, ["text"]),
    ("База знань ІІ: рецензент вимкнений за замовчуванням", "owner", "/api/knowledge/settings/", {200}, ["reviewer_enabled"]),
    ("База знань ІІ: менеджер (читання або закрито)", "manager", "/api/knowledge/items/?page_size=5", {200, 403}, []),
    ("Економіка угоди: картка (власник)", "owner", "/api/deal-economics/66164/", {200}, ["revenue", "margin", "lines", "flags"]),
    ("Економіка угоди: норми оцінок (власник)", "owner", "/api/deal-economics/settings/", {200}, ["pack_material_per_shipment", "liqpay_rate_pct"]),
    ("Економіка угоди: менеджер без права собівартості — закрито", "manager", "/api/deal-economics/66164/", {200, 403, 404}, []),
    # ── Партнерська програма (14.09.2026) ──
    ("Партнери: рівні", "owner", "/api/partners/levels/", {200}, ["levels"]),
    ("Партнери: рівні (менеджер читає для бейджів)", "manager", "/api/partners/levels/", {200}, ["levels"]),
    ("Партнери: налаштування (автознижка вимкнена)", "owner", "/api/partners/settings/", {200}, ["min_margin_pp", "auto_apply"]),
    ("Партнери: матриця знижок по папках", "owner", "/api/partners/matrix/", {200}, ["levels", "categories"]),
    ("Партнери: матриця — менеджеру без права закрито", "manager", "/api/partners/matrix/", {200, 403}, []),
    ("Партнери: знижки товару за рівнями", "owner", "/api/partners/products/1653/", {200}, ["levels"]),
    ("Партнери: товари з діючими знижками", "owner", "/api/partners/products/?page=1", {200}, ["results", "levels"]),
    ("Партнери: список і кандидати", "owner", "/api/partners/list/", {200}, ["results", "candidates"]),
    ("Партнери: історія змін знижок", "owner", "/api/partners/log/", {200}, ["results"]),
    ("Пропущені дзвінки: черга (власник)", "owner", "/api/telephony/missed/?status=open", {200}, ["results", "counts", "colleagues"]),
    ("Пропущені дзвінки: лічильник у телефоні (менеджер)", "manager", "/api/telephony/missed/summary/", {200}, ["mine", "unassigned", "max_id"]),
    ("Пропущені дзвінки: звіт по менеджерах і лініях", "owner", "/api/telephony/missed/report/", {200}, ["by_manager", "by_line", "total"]),
    ("Пропущені дзвінки: налаштування", "owner", "/api/telephony/missed/settings/", {200}, ["work_start", "sla_minutes", "escalate_minutes"]),
    ("Meta-мітки: фрази «ймовірно з реклами»", "owner", "/api/meta-attr/phrases/", {200}, ["emoji_words", "phrases", "prefixes"]),
    ("Meta-мітки: бейдж клієнта (менеджер)", "manager", "/api/meta-attr/contact/1/", {200, 404}, []),
    ("Meta-мітки: бейдж чату (менеджер)", "manager", "/api/meta-attr/conversation/1/", {200, 404}, []),
    ("Маркетинг: продажі по креативах", "owner", "/api/meta-attr/creative-sales/", {200}, ["by_ad", "likely_by_phrase", "totals"]),
    ("Біржа задач: екран (власник)", "owner", "/api/bounty/board/", {200}, ["departments", "offers", "me", "fund"]),
    ("Біржа задач: екран (менеджер бачить і бере)", "manager", "/api/bounty/board/", {200}, ["departments", "offers", "me"]),
    ("Біржа задач: мої задачі", "manager", "/api/bounty/claims/?scope=mine", {200}, ["results"]),
    ("Біржа задач: усі задачі — менеджеру без права закрито", "manager", "/api/bounty/claims/?scope=all", {403}, []),
    ("Біржа задач: підсумки місяця (власник)", "owner", "/api/bounty/summary/", {200}, ["people", "categories", "fund"]),
    ("Ставки співробітників (власник)", "owner", "/api/payroll/schemes/", {200}, ["schemes"]),
    # 17.09.2026 (Олег): ціни тонування наборів/викрасок у ставках складу; продажі з сайтів — онлайн у ЗП
    ("Ставки: ціни тонування наборів і викрасок", "owner", "/api/payroll/schemes/", {200}, ["warehouse_rates"]),
    ("Угода: варіанти тонування рядків", "owner", "DEAL_DETAIL", {200}, ["items"]),
    ("Ставки співробітників (менеджер — ні)", "manager", "/api/payroll/schemes/", {403}, []),
    ("ЗП за ставками", "owner", "/api/payroll/calc/?period=2026-08", {200}, ["rows"]),
    ("Точка беззбитковості: розшифровка фондів, ФОТ, вакансії", "owner", "/api/payroll/breakeven/", {200}, ["breakeven", "levels", "fot", "vacancies", "breakeven_with"]),
    ("Акти обʼєктів у картці клієнта", "owner", "/api/payroll/acts/?contact=1", {200}, ["results", "managers", "can_close"]),
    ("ЗП: відомість місяця", "owner", "/api/payroll/runs/?period=2026-09", {200}, ["rows", "quarter"]),
    ("Фонди зі Ставок: звʼязки (власник)", "owner", "/api/payroll/funds/links/", {200}, ["linked", "funds", "can_edit"]),
    ("Фонди зі Ставок: звʼязки (менеджер — ні)", "manager", "/api/payroll/funds/links/", {403}, []),
    ("Фінмодель: «де налаштовується» у статті", "owner", "/api/finmodel-articles/57/", {200}, ["configured_in", "linked"]),
    ("Ставки співробітників: ставки складу і розшифровка", "owner", "/api/payroll/schemes/", {200}, ["warehouse_rates", "can_edit_wh_rates", "schemes"]),
    ("Моя ЗП і KPI (менеджер, лише свої)", "manager", "/api/payroll/my/", {200}, ["has_scheme", "lines", "periods"]),
    ("Моя ЗП: чужий id — 403", "manager", "/api/payroll/my/?user=1", {403}, []),
    ("Як виконати план — правила зі схеми", "manager", "/api/payroll/my/?only=rules", {200}, ["rules"]),
    ("Моя ЗП: як прорахувалось (менеджер, лише свої)", "manager", "/api/payroll/my/detail/", {200}, ["lines", "margin_hidden"]),
    ("Моя статистика (менеджер, свої дані)", "manager", "/api/finance/salary/deals/?user=me", {200}, ["by_day", "rows"]),
    ("Моя ЗП: як прорахувалось — чужий id 403", "manager", "/api/payroll/my/detail/?user=1", {403}, []),
    # ── Розвиток v2 (16.09.2026) ──
    ("Моя ЗП: гарантовано / умовно", "manager", "/api/payroll/my/", {200}, ["guaranteed", "conditional", "has_plan"]),
    ("Моя ЗП: що буде, якщо (лише свої)", "manager", "/api/payroll/my/whatif/?pay=10000&tests=2", {200}, ["available"]),
    ("Моя ЗП: що буде, якщо — чужий id 403", "manager", "/api/payroll/my/whatif/?user=1", {403}, []),
    ("Розвиток: ти проти себе (менеджер)", "manager", "/api/gamification/me/", {200}, ["points", "season", "quality", "periods"]),
    ("Розвиток: порівняння команди закрите менеджеру", "manager", "/api/gamification/leaderboard/", {403}, []),
    ("Розвиток: порівняння команди (власник)", "owner", "/api/gamification/leaderboard/", {200}, ["managers"]),
    ("Розвиток: чужа сторінка закрита менеджеру", "manager", "/api/gamification/manager/3/", {403}, []),
    ("Розвиток: справи тижня (свої)", "manager", "/api/gamification/practice/", {200}, ["marks"]),
    ("Розвиток: налаштування (власник)", "owner", "/api/gamification/settings/", {200}, ["chat_sampling", "contests"]),
    ("Розвиток: змагання тижня (власник)", "owner", "/api/gamification/contests/", {200}, ["rows", "winners"]),
    ("Розвиток: змагання — менеджеру 403", "manager", "/api/gamification/contests/", {403}, []),
    # ── Повернення товару (16.09.2026) ──
    ("Повернення: звіт", "owner", "/api/returns/report/", {200}, ["totals", "by_reason", "by_material", "by_person", "rows"]),
    ("Повернення: блок у картці угоди (менеджер)", "manager", "/api/returns/deal/66545/", {200}, ["items", "returns", "can_money", "reasons"]),
    ("Повернення: блок у картці угоди (owner)", "owner", "/api/returns/deal/66545/", {200}, ["items", "returns", "accounts", "liqpay_refunds"]),
    ("KPI угоди без маржі", "owner", "DEAL_KPI", {200}, ["checks", "kind"]),
    ("ЗП: як прорахувалось (власник)", "owner", "/api/payroll/calc-detail/?user=102&period=2026-09", {200}, ["lines", "all_match", "run"]),
    ("ЗП: як прорахувалось (менеджер — ні)", "manager", "/api/payroll/calc-detail/?user=102&period=2026-09", {403}, []),
    ("Склад: ставки зараз у вкладці ЗП", "owner", "/api/warehouse/my-salary/?period=month", {200}, ["rates", "total"]),
    ("Склад: ставки зараз у дашборді", "owner", "/api/warehouse/dashboard/?period=month", {200}, ["rates", "rows"]),
    ("Склад: моя ЗП за один день", "owner", "/api/warehouse/my-salary/?date=2026-09-01", {200}, ["total", "label", "from", "to"]),
    ("Склад: дашборд за один день", "owner", "/api/warehouse/dashboard/?date=2026-09-01", {200}, ["rows", "label", "from", "to"]),
    ("Звільнені: де показувати (власник)", "owner", "/api/users/visibility/", {200}, ["entities", "people"]),
    ("Звільнені: де показувати (менеджер — ні)", "manager", "/api/users/visibility/", {403}, []),
    ("Табель: активні + дозволені звільнені", "owner", "/api/users/?visible_in=timesheet&period=2026-09", {200}, []),
    ("ЗП/KPI стара формула для «Планів»", "owner", "/api/finance/salary/?period=2026-09&for=plans", {200}, ["rows", "company"]),
    ("KPI складу: підказка CRM по стандарту (власник)", "owner", "/api/payroll/wh-kpi/?scheme=6&period=2026-08", {200}, ["points", "suggested_pct"]),
    ("KPI складу: підказка (менеджер — ні)", "manager", "/api/payroll/wh-kpi/?scheme=6&period=2026-08", {403}, []),
    ("Фінанси: стан закриття дня/періоду", "manager", "/api/transactions/period-lock/", {200}, ["closed_until", "day_closed_until"]),
    ("Фінанси: рахунки", "owner", "/api/accounts/", {200}, []),
    ("КПІ менеджерів", "owner", "/api/finance/salary/", {200}, []),
    ("КПІ: свої цифри (менеджер)", "manager", "/api/finance/salary/", {200, 403}, []),
    # ── Аналітика й маркетинг ──
    ("Аналітика продажів", "owner", "/api/analytics/", {200}, []),
    ("Маркетинг: основний звіт", "owner", "/api/meta-marketing/", {200}, ["sections"]),
    ("Маркетинг: GA4 + заявки сайтів", "owner", "/api/marketing/ga4/", {200}, ["sites", "crm_leads"]),
    ("Маркетинг: офлайн-воронки", "owner", "/api/marketing/offline/", {200}, []),
    ("Маркетинг: піксель", "owner", "/api/meta-marketing/pixel-events/", {200}, []),
    ("Лендинг: заявки та підсумок джерела", "owner", "/api/meta-marketing/pixel-events/?pixel=site", {200}, ["site_deals", "site_summary"]),
    ("Маркетинг закритий менеджеру без прав", "manager", "/api/meta-marketing/", {200, 403}, []),
    # ── Склад ──
    ("Склад: товари", "owner", "/api/products/?page_size=5", {200}, []),
    ("Склад: дашборд", "owner", "/api/warehouse/dashboard/", {200}, []),
    ("Склад: ЗП місяця по днях (17.09)", "owner", "/api/warehouse/my-salary/?period=calendar&which=current", {200}, ["days", "base_lines"]),
    ("Склад: моя ЗП за календарний місяць", "owner", "/api/warehouse/my-salary/?period=calendar&which=current", {200}, ["total", "piece", "base_lines"]),
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
    if url == "DEAL_KPI":
        from apps.crm.models import Deal
        deal = Deal.objects.order_by("-id").first()
        return "/api/payroll/deal-kpi/%s/" % deal.pk if deal else None
    from apps.crm.models import Contact, Deal
    if url.startswith("FUNNEL_DEALS:"):
        from apps.crm.models import Funnel
        funnel = Funnel.objects.filter(name=url.split(":", 1)[1]).first()
        return "/api/deals/?funnel=%s&page_size=5" % funnel.pk if funnel else None
    if url == "DEAL_DETAIL":
        deal = Deal.objects.order_by("-id").first()
        return "/api/deals/%s/" % deal.pk if deal else None
    if url == "CONTACT_DETAIL":
        contact = Contact.objects.order_by("-id").first()
        return "/api/contacts/%s/" % contact.pk if contact else None
    if url == "CONTACT_LEAD_QUALITY":
        contact = Contact.objects.order_by("-id").first()
        return "/api/contacts/%s/lead-quality/" % contact.pk if contact else None
    if url == "CONTACT_REVIEW_OPTOUT":
        contact = Contact.objects.order_by("-id").first()
        return "/api/reviews/opt-out/?contact_id=%s" % contact.pk if contact else None
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
