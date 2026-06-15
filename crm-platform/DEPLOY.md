# Развёртывание GMIdeas CRM на свой сервер (поддомен + HTTPS)

Итог: CRM откроется по адресу **https://crm.wallcovdec.com.ua** с автоматическим
сертификатом. Отдельный домен покупать не нужно — используем бесплатный поддомен.

Нужен сервер (у тебя есть Hetzner) с установленными **Docker** и **Docker Compose**,
и доступ к **DNS** домена `wallcovdec.com.ua`.

---

## Шаг 1. DNS — направить поддомен на сервер
В панели, где управляется домен `wallcovdec.com.ua`, добавь запись:

| Тип | Имя (host) | Значение |
|-----|------------|----------|
| `A` | `crm`      | IP-адрес твоего сервера Hetzner |

Через несколько минут `crm.wallcovdec.com.ua` будет указывать на сервер.
(Если домен за Cloudflare — поставь режим **DNS only / серое облако**, иначе мешает выдаче сертификата.)

## Шаг 2. Установить Docker на сервере (если ещё нет)
```bash
curl -fsSL https://get.docker.com | sh
```

## Шаг 3. Забрать код и настроить
```bash
git clone <URL-репозитория> gmideas
cd gmideas/crm-platform
cp .env.prod.example .env
nano .env          # укажи DOMAIN, придумай SECRET_KEY и POSTGRES_PASSWORD
```
`SECRET_KEY` сгенерировать: `openssl rand -hex 32`.

## Шаг 4. Запуск — одна команда
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
Caddy сам получит HTTPS-сертификат. Открой **https://crm.wallcovdec.com.ua**.

Демо-логины (из seed_demo): `kirill / demo12345`, `head / demo12345`.
Создать своего админа:
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

---

## Обновление после изменений в коде
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Полезное
- Логи:        `docker compose -f docker-compose.prod.yml logs -f`
- Остановить:  `docker compose -f docker-compose.prod.yml down`
- Бэкап БД:    `docker compose -f docker-compose.prod.yml exec db pg_dump -U crm crm > backup.sql`

## Что нужно от тебя, чтобы я помог развернуть
Сам сервер я отсюда не трогаю (нет доступа). Чтобы довести до рабочего URL, мне нужно
от тебя одно из двух:
1. ты выполняешь шаги 1–4 выше (я подскажу на каждом, если что-то не пойдёт), **или**
2. дашь доступ человеку/себе, кто выполнит команды — я сопровожу.

> ⚠️ Перед боевым использованием убрать демо-данные: в `docker-compose.prod.yml`
> в команде сервиса `web` удалить строку `python manage.py seed_demo &&`.
