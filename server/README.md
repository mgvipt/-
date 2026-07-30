# Цикл вдвоём — сервер-прокси (маржа на ИИ)

Бэкенд, через который идут запросы к ИИ. Клиенты платят **тебе** (подписка + кредиты),
ИИ идёт на **твоём** ключе, сервер считает расход и не пускает сверх лимита.
**Маржа = цена подписки/пакета − себестоимость LLM − комиссия платёжки.**

```
Приложение → этот сервер (твой ключ + лимиты + счётчик) → Claude/OpenAI
                     ↑ оплата клиента (ЮKassa / Stripe / Telegram)
```

## Быстрый старт (VPS)

```bash
git clone <репозиторий> && cd server
cp .env.example .env        # заполни ANTHROPIC_API_KEY, тарифы, платёжки
npm install
npm start                   # слушает :8787
```

Через Docker:
```bash
docker build -t cycle-api .
docker run -d --env-file .env -p 8787:8787 -v $PWD/data:/app cycle-api
```

Продакшн: поставь за nginx с HTTPS (Let's Encrypt), пропиши `PUBLIC_URL` и домен.
Пример nginx:
```
location /v1/ { proxy_pass http://127.0.0.1:8787; proxy_set_header Host $host; }
```

## Модель лимитов
Каждое сообщение = 1 единица. Списывается по порядку: **подписка → кредиты → бесплатный дневной лимит**.
- `FREE_DAILY` — бесплатных сообщений в день (сбрасывается ежедневно).
- Подписка: `PLAN_CAP` сообщений на `PLAN_DAYS` дней за `PLAN_PRICE`.
- Кредиты: пакеты из `CREDIT_PACKS` (не сгорают).

## Эндпоинты
| Метод | Путь | Назначение |
|---|---|---|
| POST | `/v1/account/init` | создать аккаунт устройства → `{userId, token}` |
| GET | `/v1/me` | статус лимитов/подписки/кредитов (Bearer token) |
| POST | `/v1/chat` | ответ ИИ с проверкой лимита; `402` если лимит исчерпан |
| POST | `/v1/billing/checkout` | создать оплату: `{product:"sub"}` или `{product:"credits",packId}` + `provider` |
| POST | `/v1/webhooks/{yookassa\|stripe\|telegram}` | начисление после оплаты |
| GET | `/v1/admin/stats?token=ADMIN_TOKEN` | выручка vs себестоимость LLM (маржа) |

## Платёжки
- **ЮKassa** (РФ): укажи `YOOKASSA_SHOP_ID/SECRET`, в ЛК ЮKassa настрой вебхук на `PUBLIC_URL/v1/webhooks/yookassa` (событие `payment.succeeded`).
- **Stripe** (мир): `STRIPE_SECRET` + `STRIPE_WEBHOOK_SECRET`; вебхук на `/v1/webhooks/stripe` (событие `checkout.session.completed`). Подпись проверяется.
- **Telegram**: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_PROVIDER_TOKEN`; вебхук бота на `/v1/webhooks/telegram`.
- Для «удобно всем аудиториям» подключи несколько — клиент выберет способ.

> iOS в App Store: продажу доступа к ИИ Apple требует проводить через **In-App Purchase** (комиссия 15–30%). В вебе/PWA — любая платёжка выше без комиссии Apple.

## Маржа (пример)
Себестоимость 1 сообщения: Haiku 4.5 ≈ $0.005, Sonnet 5 ≈ $0.015.
Подписка 399 ₽ / 150 сообщений на Haiku ≈ себестоимость 70 ₽ → **маржа ~300 ₽/мес** с пользователя.
Смотри факт в `/v1/admin/stats`.

## Локальный тест без ключей и платёжки
```bash
TEST_LLM=1 npm start
# в отдельном терминале — см. пример в этом README или прогонь свой скрипт:
#  POST /v1/account/init → token
#  POST /v1/chat (повторяй, пока не выйдет 402)
#  POST /v1/test/grant {product:"credits:100"}  (доступен только при TEST_LLM=1)
```

## Безопасность / масштаб
- Секреты — только в `.env`, не в git.
- Ограничь `ALLOW_ORIGIN` своим фронтендом.
- Добавь rate-limit на IP (nginx `limit_req`) от абуза.
- JSON-хранилище — для MVP; под нагрузку перенеси на Postgres (схема тривиальная: users, payments).
