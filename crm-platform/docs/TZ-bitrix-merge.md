# ТЗ: «Перенос структуры Bitrix24 в CRM gmideas/crm-platform + улучшения»

**Версия:** 1.0 · **Дата:** 2026-06-20 · **Заказчик:** Олег (Wallcov) · **Приоритет:** высокий
Источник: реальный обход Bitrix ([[Bitrix-структура-обход]]) + мультиагентный дизайн (4 домена) + [[Код-карта]].
Разделы 1–4 — простым языком (Олег), раздел 5 + код — для программиста.

---

## 1. КОНЦЕПЦИЯ

Берём из Bitrix24 всё **удобное** — кликабельную полосу стадий сверху карточки, левую колонку с полями заказа (клиент, сумма, оплачено/осталось, тип оплаты, ТТН/чек), правую ленту событий, вкладку «Товари» с гридом из каталога, карточку клиента с вкладками и историей касаний, единый «Список діалогів». Структура знакома команде — переучиваться не нужно. Стадии/поля/вкладки тянутся из API, фронт ничего не хардкодит.

Убираем **три главные боли** Bitrix:
1. **(главная)** чаты — общий поток без фильтра по ответственному, все видят всё → у нас чат привязан к ответственному, менеджер со scope «только свои» видит только переписку своих клиентов автоматически.
2. **дубли контактов ×3-4** → при входящем сообщении ищем существующий контакт по телефону/ID канала, не плодим новый.
3. **тяжёлая многотабовость (6-8 вкладок)** → всё ключевое всегда видно слева, справа 2-3 вкладки (Лента+Чат / Товары / Документы).

---

## 2. ПО СУЩНОСТЯМ

| Сущность | Повторяем из Bitrix | Улучшаем | Файлы в gmideas |
|---|---|---|---|
| **Карточка сделки** | Полоса стадий, шапка с иконками, левая колонка полей, правая лента, вкладка «Товари», КП в ленте | 2-3 вкладки вместо 6-8; чат встроен в ленту; звонки с записью+AI-оценкой; единая хронология | `frontend/src/pages/DealCard.tsx`, `crm/serializers.py`, `crm/views.py` |
| **Карточка лида** | Лид-стадии, левая колонка, зелёная «Конвертувати в Угоду+Контакт» | Создаём с нуля; конвертация переиспользует Contact | `frontend/src/pages/LeadCard.tsx` (НОВЫЙ), `LeadViewSet.convert`, `App.tsx` |
| **Карточка клиента** | Вкладки Загальне/Угоди/Рахунки/Оплата/Зв'язки, левая панель, лента касаний | Создаём с нуля; owner у контакта; авто-слияние дублей; бейдж «Можливі дублі (N)» | `frontend/src/pages/ContactCard.tsx` (НОВЫЙ), `ContactDetailSerializer`, @action |
| **Чаты (Inbox)** ⭐ | Единый список діалогів (№·Тип·Лінія·Статус·Канал·Клієнт·Дата) | **Колонка+фильтр «Відповідальний»**; RBAC «свои/все»; чипы «Мої/Всі/Не призначені»; «Передати»; чат в карточке | `Inbox.tsx`, `inbox/views.py`, `inbox/services.py`, `inbox/serializers.py` |
| **Товары в сделке** | Грид Акція·Товар·К-сть·Ціна·Сума, «Додати/Обрати товар» | Доступный остаток рядом; предупреждение qty>available | `DealCard.tsx` (вкладка Товари), `crm/views.py add_item` |
| **Каталог/Склад** | Дерево категорій + товары (Залишок·Одиниця·Ціна·Тип); табы Прибуття/Реалізація/… | Дерево самоссылочное lazy; **Доступний = stock − reserved** (Bitrix не вычитает → двойная отгрузка) | `warehouse/models.py`, `warehouse/views.py`, `Warehouse.tsx` |
| **Стадии сделки** | Полоса стадий | Полный пайплайн Wallcov склад+НП (15 стадий, is_won) | `seed_demo.py` + data-миграция |

---

## 3. ⭐ ЧАТЫ С RBAC-ПРИВЯЗКОЙ (главное требование Олега)

### Суть
Каждый клиент закреплён за ответственным. Клиент пишет в IG/Telegram/FB → чат автоматически «к ответственному». Менеджер видит только чаты своих клиентов; руководитель — все + нераспределённые. В Bitrix этого нет — главная боль.

### Диагноз (разрыв)
1. Сделки/лиды скоупятся `ScopedByRoleMixin` по `owner` — работает.
2. Чаты `ConversationViewSet.get_queryset()` фильтруются ТОЛЬКО по `allowed_channel_ids()` (канал целиком) → менеджер видит весь поток. **Это Bitrix-боль.**
3. `Conversation.assigned_to` (FK) **уже есть**, но не заполняется. Недостающее звено — заполнять при ingest + фильтровать в queryset.

### Реализация (3 шага)
**A. Contact: ответственный + поля дедупа** — `crm/models.py`: `owner` FK, `phone_normalized`, `merged_into`, `last_touch_at` + миграция + бэкфилл owner из последней сделки.

**B. ingest(): дедуп + привязка** — `inbox/services.py`: искать существующий Contact по `phone_normalized`/`external_chat_id` ПЕРЕД созданием; `Conversation.assigned_to = contact.owner` (или owner активной сделки); ⚠️ если не определить — `assigned_to=None` («Не призначені»), **никогда** не fallback на pilot-юзера (утечка чужих чатов).

**C. Фильтрация по роли** — `accounts/models.py`: права `conversation.view.own/all` + хелпер `can_see_all_conversations()`; `inbox/views.py` `get_queryset()`: если нет права «все» → `filter(assigned_to=user) | filter(contact__owner=user)`.

### Эндпоинты
- `GET /api/conversations/?scope=mine|all|unassigned` — фильтр-чипы.
- `POST /api/conversations/{id}/assign/` — переброс (только `view.all`/`roles.manage`).
- `GET /api/deals/{id}/conversation/` — чат контакта сделки (новый @action).

### UI
- `Inbox.tsx`: таблица + колонка **ВІДПОВІДАЛЬНИЙ** + чипы «Мої/Всі/Не призначені» + «Передати».
- `DealCard.tsx` блок [11.1]: заменить заглушку на реальный чат (load messages, send).
- `DealDetailSerializer`: скрыть `margin/bonus` без `deal.view.all`.

---

## 4. СТАДИИ СДЕЛКИ — пайплайн Wallcov (15 стадий)

| # | Стадия | Цвет | Флаг | Группа |
|---|---|---|---|---|
| 1 | Дані для розрахунку | #3b82f6 | — | заявка |
| 2 | Розрахунок | #6366f1 | — | заявка |
| 3 | Домовились | #8b5cf6 | — | заявка |
| 4 | Оплата отримана | #f59e0b | — | оплата |
| 5 | Заброньовано | #f59e0b | — | резерв |
| 6 | Відвантаження | #10b981 | — | резерв |
| 7 | Тонування | #10b981 | — | резерв |
| 8 | Пакування (склад) | #10b981 | — | резерв |
| 9 | НП ТТН створено | #0ea5e9 | — | резерв |
| 10 | НП Відправлено | #0ea5e9 | — | резерв |
| 11 | НП В дорозі | #0ea5e9 | — | резерв |
| 12 | НП Прибуло | #0ea5e9 | — | резерв |
| 13 | НП На відділенні | #0ea5e9 | — | резерв |
| 14 | Отримано | #16a34a | is_won | финал |
| 15 | Завершити | #16a34a | is_won | финал |

`RESERVING_STAGES` = 5–13 → `available() = stock() − reserved()`.
Засев: новые инсталляции — `seed_demo.py` (get_or_create); прод — **data-migration или Django-admin**, НЕ seed (дубли).

---

## 5. ПРИОРИТИЗИРОВАННЫЙ ПЛАН

### Этап 0 — Фундамент данных (модели+миграции)
- 0.1 `Contact`: +`owner`,`phone_normalized`,`merged_into`,`last_touch_at` + норм. телефона в `save()` — `crm/models.py`
- 0.2 makemigrations+migrate+бэкфилл owner — `crm/migrations/`
- 0.3 `PERMISSION_CHOICES`: +`conversation.view.own/all`,`inbox.view_all`,`warehouse.manage` + `can_see_all_conversations()` — `accounts/models.py`
- 0.4 Пайплайн 15 стадий + data-migration — `seed_demo.py`+`crm/migrations/`

### Этап 1 — ⭐ Чаты с RBAC (главное)
- 1.1 `ingest()`: дедуп + `assigned_to` без pilot-fallback — `inbox/services.py`
- 1.2 `ConversationViewSet.get_queryset()`: уровень 2 (assigned_to/contact__owner) + filterset — `inbox/views.py`
- 1.3 `@action assign/` + `?scope=` — `inbox/views.py`
- 1.4 `ConversationSerializer`: +`assigned_to_name` — `inbox/serializers.py`
- 1.5 `Inbox.tsx`: колонка Відповідальний + чипы + «Передати»
- 1.6 `api.ts`: `assignConversation()`

### Этап 2 — Карточка сделки: таймлайн + чат
- 2.1 `DealViewSet`: `@action conversation/` + обёртки create_ttn/issue_receipt/liqpay над `integrations/adapters.py` — `crm/views.py`
- 2.2 `DealDetailSerializer`: `timeline` (оплаты+звонки+сообщения+стадии) + `conversation_id` + скрыть margin/bonus — `crm/serializers.py`
- 2.3 `DealCard.tsx` [11.1]: реальный чат
- 2.4 `DealCard.tsx` [6]: лента = оплаты+звонки(recording+AI)+сообщения+стадии
- 2.5 `DealCard.tsx` [9]/[5]: боевые ТТН/чек/ссылка

### Этап 3 — Карточки лида и клиента
- 3.1 `LeadViewSet.convert/` · 3.2 `LeadCard.tsx` (НОВЫЙ) · 3.3 `ContactViewSet` scope+@action · 3.4 `ContactDetailSerializer` · 3.5 `ContactCard.tsx` (НОВЫЙ)+merge · 3.6 `App.tsx` роуты · 3.7 `dedup_contacts.py` (DRY_RUN→merge, три шага)

### Этап 4 — Каталог/склад
- 4.1 `ProductCategory`+`reserved()/available()` · 4.2-4.4 сериализаторы/вьюсеты/роуты · 4.5 `add_item` проверка остатка · 4.6 `Warehouse.tsx` дерево · 4.7 `DealCard` модалка-каталог · 4.8 `api.ts`

### Правила безопасности
Дедуп/merge >5 записей — DRY_RUN→тест→LIVE, перенос не удаление, право `roles.manage`. Прод-стадии — data-migration/admin не seed. `assigned_to=None` без fallback. Миграции — makemigrations отдельно, ревью SQL.

> ⚠️ Пути/имена сверены с CODEMAP, но не с живым кодом. Перед Этапом 0 подтвердить: имя `Conversation.assigned_to` + значения `status`; `ScopedByRoleMixin.view_all_method`; сигнатуру `ingest()`; формат `Contact.channels`; существующие `filterset_fields`.

> Updated [[Daily/2026-06-20]] — ТЗ переноса Bitrix готово. Связано: [[Bitrix-структура-обход]], [[Merge-план]], [[Код-карта]].
