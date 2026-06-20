# Код-карта CRM (gmideas/crm-platform)

> Документ для владельца и для программиста, который заходит в проект впервые.
> Версия от 2026-06-20. Репозиторий на сервере: `/root/gmideas/crm-platform`. Live: https://crm.wallcovdec.com.ua
> Всё ниже — по факту кода (read-only-аудит), без догадок.

---

## 1. Обзор стека

Это самостоятельная CRM «GMIdeas» (бренд в интерфейсе — «GMIdeas CRM»), написанная с нуля как замена Битрикс24 + Finmap для Wallcov. **Бэкенд** — Django 5 + Django REST Framework, кастомная модель пользователя, авторизация по токену (`rest_framework.authtoken`), БД PostgreSQL 16 в проде (SQLite как fallback для локального запуска), пагинация по 50, фильтры через `django-filters`. **Фронтенд** — React + TypeScript (Vite), маршрутизация `react-router-dom`, стили — обычный CSS (`styles.css`) + инлайн-стили, без UI-библиотек. Бэкенд разбит на 8 Django-приложений (`backend/apps/*`), фронт — на страницы (`frontend/src/pages/*.tsx`). Связь — единый REST API под `/api/`.

**Как запускается / деплоится** (всё в Docker, 3 контейнера: `db` Postgres, `web` Django+gunicorn, `caddy` сборка фронта + reverse-proxy):

```bash
# Развёртывание одной командой (ставит Docker, создаёт .env, поднимает стек):
cd /root/gmideas/crm-platform
sudo bash deploy.sh

# Или вручную:
cp .env.prod.example .env && nano .env          # DOMAIN, SECRET_KEY, пароли Postgres
docker compose -f docker-compose.prod.yml up -d --build

# Пересобрать только фронт (после правок frontend/):
docker compose -f docker-compose.prod.yml build caddy && docker compose -f docker-compose.prod.yml up -d caddy
# Пересобрать бэк (после правок backend/, авто-применит миграции при старте):
docker compose -f docker-compose.prod.yml build web && docker compose -f docker-compose.prod.yml up -d web
```

Что происходит при старте контейнера `web` (см. `docker-compose.prod.yml`): `migrate` → `collectstatic` → `seed_demo` (демо-роли/воронки/лиды) → `gunicorn ... -w 3`. Контейнер `caddy` (см. `deploy/Dockerfile.caddy`) сначала собирает фронт (`npm ci && npm run build` → `/srv`), потом раздаёт SPA и проксирует `/api/`, `/admin/`, `/static/` на `web:8000`. Caddy слушает только `127.0.0.1:${EDGE_PORT:-8137}` — публичные 80/443 и TLS держит системный nginx (он же проксирует поддомен CRM сюда; конфиг-образец `deploy/nginx-crm.conf`).

**Демо-доступы** (из `seed_demo.py` / `deploy.sh`): `director / demo12345` (полный доступ), `head / demo12345` (руководитель), `kirill` и `ilona` `/ demo12345` (менеджеры). Создать своего админа: `docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser`.

---

## 2. Карта модулей backend

Глобальные роуты собираются в `backend/config/urls.py` через `DefaultRouter` (ViewSet-ы) + отдельные `path()` (APIView). Все приложения подключены в `backend/config/settings.py` → `INSTALLED_APPS`. Все эндпоинты под префиксом `/api/`.

| App (`backend/apps/X`) | За что отвечает | Ключевые модели (`models.py`) | Ключевые эндпоинты (метод + путь + что делает) |
|---|---|---|---|
| **accounts** | Пользователи, роли, права (RBAC), отделы | `User` (расширяет `AbstractUser`, поля `role`, `department`, `phone`, `theme`), `Role` (`permissions` JSON + M2M `funnels` + `open_lines`), `Department`. Каталог прав — константа `PERMISSION_CHOICES` | `GET/POST/PATCH /api/roles/` `/api/users/` (только право `roles.manage`, см. `RoleViewSet.required_perm`); `GET /api/me/` — текущий юзер + его права + каталог прав (для фронта); `PATCH /api/me/` — сотрудник меняет только свою тему (`theme`) |
| **crm** | Ядро: контакты, компании, воронки, стадии, лиды, сделки, товары в сделке, оплаты, аналитика | `Company`, `Contact` (телефон, `channels` JSON, `loyalty_tag`, `birthday`), `Funnel` (`is_lead_funnel`), `Stage` (`color`, `order`, `is_won`, `is_lost`), `Lead`, `Deal` (`amount`, `discount_pct`, `pay_type`, `ttn`, `checkbox_status`, `closed_at`), `DealItem` (товар×кол-во×цена), `Payment` (provider liqpay/checkbox/cash/bank) | CRUD: `/api/contacts/ /api/companies/ /api/funnels/ /api/stages/ /api/leads/ /api/deals/ /api/payments/`. **@action на сделке** (`DealViewSet`): `POST /api/deals/{id}/add_item/`, `POST /api/deals/{id}/remove_item/` (пересчёт суммы), `POST /api/deals/{id}/accept_payment/` (→ доход в финансы), `POST /api/deals/{id}/ship/` (списание со склада + расход себестоимости). `GET /api/analytics/?funnel=` — KPI + воронка по стадиям + топ менеджеров (`AnalyticsView`) |
| **inbox** | «Открытые линии» — чаты с клиентами через мессенджеры (пока реально Telegram) | `Channel` (kind telegram/viber/…, `config` JSON с секретами — наружу не отдаётся), `Conversation` (`external_chat_id`, `unread`, `assigned_to`), `Message` (`direction` in/out, `attachments` JSON) | `GET /api/channels/`, `GET /api/conversations/` (read-only); `GET /api/conversations/{id}/messages/` (сбрасывает unread); `POST /api/conversations/{id}/send/` (шлёт через адаптер канала); `POST /api/inbox/telegram/webhook/{channel_id}/` — публичный приём апдейтов Telegram (`AllowAny`) |
| **warehouse** | Товары и складской учёт (приход/расход/инвентаризация) | `Warehouse` (`is_default`), `Product` (`price`, `cost` себестоимость, `sku`; метод `stock()`), `StockDocument` (kind in/out/inv, привязка к `deal`), `StockMovement` (строка-движение, ±qty) | CRUD: `/api/warehouses/ /api/products/ /api/stock-documents/`. Остаток товара (`stock`) считается на лету как сумма движений. Создание `StockDocument` через сериализатор сам проставляет знак qty (расход = минус) |
| **finance** | Финмодуль (замена Finmap): счета, категории, проводки, дашборд | `Account` (kind bank/cash/acquiring; метод `balance()`), `Category` (direction in/out), `Transaction` (direction, `amount`, `account`, `category`, привязки к `deal` и `payment`) | CRUD: `/api/accounts/ /api/categories/ /api/transactions/` (все под правом `finance.view`, см. `FinancePerm`); `GET /api/finance/dashboard/` — остаток на счетах, доход/расход/прибыль за месяц, денежный поток за 30 дней. Логика проводок — `finance/services.py`: `record_income()`, `record_expense()` |
| **integrations** | Хранение ключей внешних сервисов + вызовы LiqPay / Нова Пошта / Checkbox | `IntegrationSettings` (provider liqpay/checkbox/novaposhta, `config` JSON, `is_active`) | `GET/POST /api/integrations/settings/` — чтение (ключи маскируются) и сохранение, право `roles.manage`; `POST /api/integrations/liqpay/link/` — генерит ссылку на оплату; `POST /api/integrations/novaposhta/track/` — статус ТТН. Сами вызовы API — `integrations/adapters.py` |
| **telephony** | Журнал звонков (через SIP-шлюз/Asterisk) | `Call` (direction in/out/missed, `from_number`, `to_number`, `duration`, `recording_url`, привязки к `contact`/`deal`/`manager`) | `GET/POST /api/calls/`; `GET /api/calls/stats/` — всего/записано/пропущено/средняя длительность; `POST /api/telephony/webhook/` — публичный приём события от SIP-шлюза после звонка (`AllowAny`), сам находит контакт по номеру |
| **common** | Общий код прав (не Django-app в полном смысле) | — | Класс `HasPermCode` (`permissions.py`) — проверяет `view.required_perm` против роли пользователя. Используется во всех защищённых вьюсетах |

**Управляющие команды** (`manage.py`): `seed_demo` (демо-данные, `apps/crm/management/commands/`), `telegram_channel --token --name --domain` (создаёт Telegram-канал и выставляет webhook, `apps/inbox/management/commands/`).

---

## 3. Карта экранов frontend

Роутинг — `frontend/src/App.tsx` (если нет `me` — рендерит `Login`, иначе `Layout` с вложенными роутами). Авторизация и проверка прав — `frontend/src/auth.tsx` (хук `useAuth()`, метод `can(code)`). REST-клиент и типы — `frontend/src/api.ts` (токен в `localStorage`, заголовок `Authorization: Token …`). Общие UI-компоненты (`Avatar`, `SourceChip`) — `frontend/src/ui.tsx`.

| Страница (файл) | Что показывает | Какие API дёргает |
|---|---|---|
| **Login.tsx** | Форма входа | `POST /api/auth/token/` (через `login()` в `api.ts`) |
| **Layout.tsx** | Каркас: сайдбар-меню (пункты фильтруются по правам через `can(perm)`), топбар, переключатель темы | `PATCH /api/me/` (сохранить тему). Список меню `NAV` с требуемыми правами задан прямо в файле |
| **Leads.tsx** | Канбан лидов (берёт воронку с `is_lead_funnel`) | `GET /api/funnels/` → отдаёт `Board` |
| **Deals.tsx** | Канбан сделок с выбором воронки продаж | `GET /api/funnels/` → `Board` |
| **Board.tsx** | Универсальный канбан (общий для лидов и сделок). Drag&drop карточки между колонками = смена стадии. Клик по сделке → её карточка | `GET {endpoint}?funnel=…&page_size=200`; `PATCH {endpoint}{id}/ {stage}` при переносе |
| **DealCard.tsx** | Карточка сделки: стадии (кликабельны), клиент+лояльность, сумма/оплачено/осталось, скидка, ТТН/Checkbox, маржа+бонус, товары, лента событий, приём оплаты, отгрузка | `GET /api/deals/{id}/`, `GET /api/funnels/{id}/`, `GET /api/products/`; `PATCH /api/deals/{id}/`; `POST .../add_item/`, `.../remove_item/`, `.../accept_payment/`, `.../ship/` |
| **Inbox.tsx** | Чаты/открытые линии: список диалогов + переписка, отправка сообщений | `GET /api/conversations/`; `GET /api/conversations/{id}/messages/`; `POST /api/conversations/{id}/send/` |
| **Clients.tsx** | Таблица контактов с поиском | `GET /api/contacts/?search=…` |
| **Finance.tsx** | Финдашборд: 4 KPI-карточки, график денежного потока за 30 дней, список счетов. Виден только с правом `finance.view` | `GET /api/finance/dashboard/` |
| **Warehouse.tsx** | Таблица товаров с остатками/себестоимостью + модалки прихода/расхода | `GET /api/products/`, `GET /api/warehouses/`; `POST /api/stock-documents/` |
| **Analytics.tsx** | Сводка продаж: KPI, воронка по стадиям, топ менеджеров, фильтр по воронке | `GET /api/analytics/?funnel=` |
| **Phone.tsx** | Журнал звонков + статистика | `GET /api/calls/?page_size=200`, `GET /api/calls/stats/` |
| **Roles.tsx** | Матрица ролей × прав (галочки выдают права, сразу сохраняются) | `GET /api/roles/`, `GET /api/me/` (каталог прав); `PATCH /api/roles/{id}/` |
| **Settings.tsx** | Настройки интеграций (ключи LiqPay/Checkbox/Нова Пошта, маскируются) | `GET /api/integrations/settings/`; `POST /api/integrations/settings/` |

---

## 4. «Где менять типовые вещи»

Порядок действий для самых частых задач. Все пути от корня `/root/gmideas/crm-platform`.

| Сценарий | Что и где менять (по шагам) |
|---|---|
| **Добавить поле в сделку** | 1. `backend/apps/crm/models.py` → класс `Deal`, добавить поле. 2. Создать миграцию: `manage.py makemigrations crm && migrate`. 3. `backend/apps/crm/serializers.py` → `DealSerializer.Meta.fields` (добавить имя поля). 4. На фронте: `frontend/src/pages/DealCard.tsx` — интерфейс `Deal` + вывод/редактирование поля (через `patch({...})`). При необходимости — тип `Card` в `frontend/src/api.ts`. |
| **Добавить кнопку-действие в карточку сделки** | Бэк: `backend/apps/crm/views.py` → `DealViewSet`, новый метод с `@action(detail=True, methods=["post"])` (примеры рядом: `accept_payment`, `ship`). Фронт: `frontend/src/pages/DealCard.tsx` — функция-обработчик вызывает `api.post('/api/deals/{id}/ваш_action/')` + кнопка в JSX (блок «быстрые действия» или шапка). |
| **Добавить стадию воронки** | Стадии — это записи модели `Stage` в БД, не код. Способы: через Django-admin (`/admin/`, модель Stage) или в `backend/apps/crm/management/commands/seed_demo.py` (списки `LEAD_STAGES`/`DEAL_STAGES`) для новых инсталляций. Ключевые поля стадии: `order` (порядок), `color`, `is_won`/`is_lost` (won влияет на выручку в аналитике). Фронт ничего менять не нужно — `Board`/`DealCard` берут стадии из `GET /api/funnels/`. |
| **Новый отчёт в финмодуле** | Бэк: либо новый `@action` в `backend/apps/finance/views.py` (`TransactionViewSet`), либо новый `APIView` + строка в `backend/config/urls.py` (как `FinanceDashboardView` → `/api/finance/dashboard/`). Не забыть `permission_classes = [FinancePerm]`. Фронт: новый блок в `frontend/src/pages/Finance.tsx` или новая страница в `pages/` + роут в `App.tsx` + пункт меню в `Layout.tsx` (`NAV`). |
| **Подключить новый канал в inbox** (Viber/Instagram/WhatsApp) | `backend/apps/inbox/adapters.py` — добавить класс-наследник `ChannelAdapter` (методы `parse_webhook` и `send`), зарегистрировать в словаре `ADAPTERS`. Если нужен входящий webhook — добавить `APIView` в `inbox/views.py` + роут в `config/urls.py` (по образцу `TelegramWebhookView`). Канал заводится записью `Channel`. Логика приёма/отправки (`ingest`, `send_message`) в `inbox/services.py` канал-независима. |
| **Изменить права роли (RBAC)** | Каталог прав — `backend/apps/accounts/models.py` → константа `PERMISSION_CHOICES`. Применение: `permission_classes=[HasPermCode]` + `required_perm="код"` (см. `common/permissions.py`), либо отдельный класс (пример `FinancePerm`). Видимость «свои/все» — миксин `ScopedByRoleMixin` в `crm/views.py`. Доступ к воронкам — M2M `Role.funnels` + `User.allowed_funnel_ids()`. Выдача галочками — экран `frontend/src/pages/Roles.tsx`. Скрытие меню — `can(perm)` в `Layout.tsx`. |

---

## 5. Поток данных сделки: лид → сделка → оплата (→ финансы) → отгрузка (→ склад)

1. **Лид** (`crm.Lead`). Источник: менеджер вручную, либо сообщение в чат → `inbox/services.py:ingest()` заводит `Contact` и `Conversation`. Лид в воронке `is_lead_funnel=True`, двигается drag&drop (`Board.tsx` → `PATCH /api/leads/{id}/ {stage}`). Бейдж «НЕПЕРЕГЛЯНУТІ» — поле `is_seen`.
2. **Сделка** (`crm.Deal`). В воронке продаж, тот же `Contact`. Видимость — `ScopedByRoleMixin` фильтрует по `owner` и разрешённым воронкам.
3. **Товары** (`crm.DealItem`). `add_item/`/`remove_item/` → `DealViewSet._recalc_amount()` пересчитывает `Deal.amount`.
4. **Оплата → финансы**. `accept_payment/` создаёт `crm.Payment(is_paid=True)` + `finance.services.record_income()` → `Transaction(direction="in")`. Попадает в дашборд и аналитику.
5. **Отгрузка → склад → себестоимость**. `ship/`: `StockDocument(kind="out")` + `StockMovement(−qty)` по `product.cost`; COGS расходом через `record_expense()` → `Transaction(direction="out")`. Так считается маржа.
6. **Документы**. ТТН (`Deal.ttn`) и чек Checkbox (`Deal.checkbox_status`) — из карточки (сейчас заглушки через `PATCH`; боевые вызовы готовы в `integrations/adapters.py`).

**Маржа и бонус** — `crm/serializers.py:DealDetailSerializer` (`get_margin` = выручка − себестоимость или 35% оценка; `get_bonus` ≈ 2% оборота).

---

## 6. Точки интеграции с системами Wallcov (Cashflow / Checkbox / Нова Пошта / AI-РОП)

Все внешние интеграции — в `backend/apps/integrations/`. Ключи в таблице `IntegrationSettings` (по записи на провайдера), заводятся на экране **Настройки** (`frontend/src/pages/Settings.tsx`). Вызовы — `integrations/adapters.py`, работают только при `is_active=True`.

| Система Wallcov | Где в коде | Статус / как подключить |
|---|---|---|
| **LiqPay / оплаты (≈Cashflow-платежи)** | `integrations/adapters.py:liqpay_checkout_link()`, вью `LiqpayLinkView` → `POST /api/integrations/liqpay/link/`. Ключи: `public_key`, `private_key`, `currency` | Готово. Ввести ключи в Настройках → включить. Кнопку «Ссылка на оплату» в `DealCard.tsx` (сейчас заглушка) привязать к этому эндпоинту. |
| **Checkbox / фискальные чеки** | `integrations/adapters.py:checkbox_create_receipt()`. Ключи: `token`, `license_key`. На сделке — `Deal.checkbox_status` | Вызывает `api.checkbox.ua/api/v1/receipts/sell`. Для боевого режима: добавить `@action` в `DealViewSet`, собирающий товары и вызывающий `checkbox_create_receipt()`. |
| **Нова Пошта** | `integrations/adapters.py:np_track()` (статус, `NovaPoshtaTrackView` → `/api/integrations/novaposhta/track/`) и `np_create_ttn()` (создание — адаптер есть, обёртки нет). Ключи: `api_key`, `sender_*` | Трекинг готов. Для автосоздания ТТН: `@action` в `DealViewSet` → `np_create_ttn(props)` → записать в `Deal.ttn`. Сейчас кнопка «Создать ТТН» — заглушка. |
| **AI-РОП / внешние чаты (ChatPlace, B24-Relay)** | Прямой интеграции нет. Точка входа — app **inbox**: `Channel` + адаптеры + webhook. Реализован только `TelegramAdapter` | Завести адаптер канала (раздел 4) или слать входящие на webhook. Связь «канал → лид/контакт» — `inbox/services.py:ingest()`. |

**Безопасность (по факту кода):** секреты каналов (`Channel.config`) и ключи интеграций наружу не отдаются (`ChannelSerializer` исключает `config`, `IntegrationSettingsView` маскирует). Доступ к интеграциям — право `roles.manage`.
