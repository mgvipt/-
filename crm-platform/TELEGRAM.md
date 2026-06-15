# Подключение Telegram (открытая линия)

Telegram-инбокс работает через **бота**: клиенты пишут боту, сообщения падают в CRM
в раздел «Чаты», ты отвечаешь из CRM — ответ уходит клиенту в Telegram.

## 1. Создать бота
1. В Telegram напиши **@BotFather** → `/newbot`.
2. Задай имя и username бота.
3. Скопируй **токен** (вид `123456:ABC-DEF...`).

## 2. Зарегистрировать канал в CRM
На сервере (где запущен бэкенд):
```bash
docker compose -f docker-compose.prod.yml exec web \
  python manage.py telegram_channel --token "ТОКЕН" --name "Wallcov бот" --domain crm.wallcovdec.com.ua
```
Команда создаст открытую линию и **сама выставит webhook** на
`https://crm.wallcovdec.com.ua/api/inbox/telegram/webhook/<id>/`.

> Локально (без публичного домена) webhook Telegram не примет — нужен HTTPS-домен.
> Поэтому Telegram проверяется уже на развёрнутом сервере.

## 3. Проверить
1. Напиши своему боту в Telegram любое сообщение.
2. В CRM открой «Чаты · Открытые линии» — появится диалог. Ответь — придёт в Telegram.

## Права на открытые линии
В роли сотрудника поле **open_lines** = список id каналов, которые ему видны.
Пусто = видит все линии. Так менеджеру можно дать только нужную линию.

## Как это устроено (для разработки)
- `apps/inbox/adapters.py` — `TelegramAdapter` (разбор webhook + отправка). Новые каналы
  (Viber/Instagram/WhatsApp) добавляются новым адаптером без изменения инбокса.
- `apps/inbox/services.py` — `ingest()` (входящее → контакт+диалог+сообщение), `send_message()`.
- Webhook: `POST /api/inbox/telegram/webhook/<channel_id>/` (публичный).
- API: `/api/conversations/`, `/api/conversations/<id>/messages/`, `POST .../send/`.
