# GMIdeas CRM — Backend (CRM-ядро)

Django + DRF. Этап 1: лиды, сделки, воронки, контакты, **роли/права (RBAC)**, перенос оплат.

## Быстрый старт (локально, SQLite)
```bash
cd crm-platform/backend
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # демо-роли, воронки, лиды
python manage.py createsuperuser    # для входа в /admin
python manage.py runserver
```
Открыть: `http://localhost:8000/admin/` и API `http://localhost:8000/api/`.

## Через Docker (PostgreSQL + Redis + MinIO)
```bash
docker compose up --build
```

## Демо-логины (после seed_demo)
| Логин | Роль | Что видит |
|---|---|---|
| `head` | Руководитель отдела | все лиды/сделки отдела |
| `ilona`, `kirill` | Менеджер | только свои лиды, только воронка «21» |

Пароль у всех: `demo12345`.

## Тесты
```bash
python manage.py test
```
`apps/crm/tests.py` проверяет ключевую логику прав: «свои vs все лиды» и ограничение по воронкам.

## API (основное)
| Endpoint | Назначение |
|---|---|
| `GET /api/me/` | текущий пользователь + его права + каталог прав (для меню фронта) |
| `PATCH /api/me/` | сотрудник меняет свою тему оформления (фон/акцент) |
| `/api/leads/` `/api/deals/` | канбан-данные (фильтруются по правам автоматически) |
| `/api/funnels/` | воронки со стадиями (только доступные роли) |
| `/api/roles/` `/api/users/` | управление ролями/сотрудниками (право `roles.manage`) |
| `/api/payments/` | оплаты (LiqPay/Checkbox/наличка) |

## Модель прав (RBAC)
- Роли **динамические**: администратор создаёт роль и набирает права из каталога (`accounts.models.PERMISSION_CHOICES`).
- Видимость: `lead.view.own` / `lead.view.all` (и аналогично для сделок).
- Доступ к воронкам: задаётся per-роль (`Role.funnels`). Пусто = все воронки.
- `finance.view`, `warehouse.view`, `telephony.view` — гейтят будущие модули.

## Дальше
Следующие модули (inbox, телефония, склад, финансы) подключаются как Django-приложения
рядом, переиспользуя `Contact`/`Deal`/RBAC. См. `../ARCHITECTURE.md`.
