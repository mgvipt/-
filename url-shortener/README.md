# URL Shortener

Самохостинг-сервис коротких ссылок. Лёгкий, без внешних зависимостей: Node.js + Express + SQLite (через `better-sqlite3`). Работает одним процессом, данные — в одном файле. Идеально подходит для Hetzner Cloud CX-инстанса.

Возможности:
- Создание коротких ссылок с автоматическим или кастомным кодом (`/promo`).
- Счётчик кликов и дата последнего перехода.
- Заметка к каждой ссылке.
- Веб-интерфейс на `/admin`, защищённый токеном.
- REST API с авторизацией по `Bearer`-токену.
- Чистые редиректы `302` на `/<slug>`.
- Развёртывание одной командой: systemd + Caddy (TLS автоматический).

Проект лежит в подкаталоге `url-shortener/` репозитория. Все команды ниже выполняются из этого подкаталога.

## Быстрый старт локально

Требуется Node.js ≥ 18.

```bash
cd url-shortener
cp .env.example .env
# отредактируйте ADMIN_TOKEN
npm install
npm start
```

Откройте http://localhost:3000/admin, введите токен.

## Деплой на Hetzner (Ubuntu/Debian)

Предположения: у вас домен, A/AAAA-запись ведёт на IP сервера, и доступ по SSH как root.

### 1. Подготовить сервер

```bash
ssh root@your-server
apt update && apt upgrade -y
apt install -y curl git ufw openssl
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

### 2. Установить приложение

Вариант А — скриптом (после публикации этого репозитория):

```bash
git clone https://github.com/<your-user>/<your-repo>.git /tmp/url-shortener
REPO_URL=https://github.com/<your-user>/<your-repo>.git \
  bash /tmp/url-shortener/deploy/install.sh
```

Вариант Б — вручную:

```bash
# Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs build-essential

# пользователь и каталог
useradd --system --home /opt/url-shortener --shell /usr/sbin/nologin shortener
git clone <repo> /opt/url-shortener
mkdir -p /opt/url-shortener/data
chown -R shortener:shortener /opt/url-shortener

# зависимости
sudo -u shortener -H bash -lc 'cd /opt/url-shortener && npm install --omit=dev'

# .env
cat >/opt/url-shortener/.env <<EOF
HOST=127.0.0.1
PORT=3000
PUBLIC_BASE_URL=https://links.example.com
ADMIN_TOKEN=$(openssl rand -hex 32)
DB_PATH=/opt/url-shortener/data/shortener.db
EOF
chown shortener:shortener /opt/url-shortener/.env
chmod 600 /opt/url-shortener/.env

# systemd
install -m 644 /opt/url-shortener/deploy/url-shortener.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now url-shortener
```

### 3. TLS и публикация через Caddy (рекомендуется)

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  > /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

# подставьте свой домен в Caddyfile
cp /opt/url-shortener/deploy/Caddyfile /etc/caddy/Caddyfile
nano /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy сам получит Let's Encrypt-сертификат.

Если предпочитаете Nginx — используйте `deploy/nginx.conf.example` вместе с `certbot --nginx`.

### 4. Проверка

```bash
systemctl status url-shortener
journalctl -u url-shortener -f
curl -I https://links.example.com/health
```

Откройте `https://links.example.com/admin`, вставьте `ADMIN_TOKEN` из `.env`.

## API

Все эндпойнты под `/api/*` требуют заголовок `Authorization: Bearer <ADMIN_TOKEN>` либо `X-Admin-Token: <ADMIN_TOKEN>`.

### Создать ссылку

```bash
curl -X POST https://links.example.com/api/links \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/very/long","slug":"promo","note":"кампания 2026"}'
```

Ответ:
```json
{
  "slug": "promo",
  "short_url": "https://links.example.com/promo",
  "target": "https://example.com/very/long",
  "created_at": 1713600000000,
  "clicks": 0,
  "last_click_at": null,
  "note": "кампания 2026"
}
```

### Список ссылок
`GET /api/links?limit=100&offset=0`

### Обновить цель/заметку
`PATCH /api/links/:slug` с телом `{ "url": "...", "note": "..." }`

### Удалить
`DELETE /api/links/:slug`

### Редирект
`GET /:slug` → `302` на целевой URL и `+1` к счётчику.

## Безопасность

- Токен хранится только на сервере в `.env` с правами `600`.
- Сравнение токена — через `crypto.timingSafeEqual`.
- Запрещены зарезервированные slug-и (`api`, `admin`, `health`…).
- Принимаются только `http://` и `https://` URL.
- systemd-юнит запускается с `NoNewPrivileges`, `ProtectSystem=strict`, ограниченной ФС.
- Для дополнительной защиты админки можно ограничить `/admin` и `/api/*` по IP через Caddy (пример в `deploy/Caddyfile`).

## Бэкап

Достаточно скопировать файл БД:

```bash
sudo -u shortener sqlite3 /opt/url-shortener/data/shortener.db ".backup /root/shortener-$(date +%F).db"
```

Хорошо сочетается с Hetzner Storage Box по SFTP или с `restic`/`borg`.

## Обновление

```bash
cd /opt/url-shortener
sudo -u shortener git pull
sudo -u shortener npm install --omit=dev
systemctl restart url-shortener
```

## Структура

```
server.js                 — HTTP-сервер + API + редиректы
public/index.html         — публичная главная
public/admin.html         — админка (вход по токену)
public/admin.js           — логика админки
public/styles.css         — стили
public/404.html           — страница «не найдено»
deploy/url-shortener.service — systemd-юнит
deploy/Caddyfile          — пример reverse-proxy + TLS
deploy/nginx.conf.example — альтернатива для Nginx
deploy/install.sh         — скрипт одноразовой установки
```
