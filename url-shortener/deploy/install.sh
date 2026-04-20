#!/usr/bin/env bash
# Установщик URL-сокращателя для Debian/Ubuntu на Hetzner.
# Запускать от root: sudo bash deploy/install.sh

set -euo pipefail

APP_DIR=/opt/url-shortener
APP_USER=shortener
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-claude/url-shortener-app-p1rdS}"
# Подкаталог внутри репозитория, где лежит приложение
SRC_SUBDIR="${SRC_SUBDIR:-url-shortener}"
CHECKOUT_DIR=/opt/url-shortener-src

if [[ $EUID -ne 0 ]]; then
  echo "Запускайте через sudo." >&2
  exit 1
fi

echo "==> Устанавливаю Node.js 20 и зависимости"
if ! command -v node >/dev/null || [[ "$(node -v | cut -dv -f2 | cut -d. -f1)" -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
apt-get install -y build-essential git ca-certificates rsync

echo "==> Создаю системного пользователя $APP_USER"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"

echo "==> Клонирую / обновляю исходники в $CHECKOUT_DIR"
if [[ -d "$CHECKOUT_DIR/.git" ]]; then
  git -C "$CHECKOUT_DIR" fetch origin "$BRANCH"
  git -C "$CHECKOUT_DIR" checkout "$BRANCH"
  git -C "$CHECKOUT_DIR" reset --hard "origin/$BRANCH"
else
  if [[ -z "$REPO_URL" ]]; then
    echo "Укажите переменную REPO_URL с адресом git-репозитория." >&2
    exit 1
  fi
  git clone --branch "$BRANCH" "$REPO_URL" "$CHECKOUT_DIR"
fi

echo "==> Синхронизирую $CHECKOUT_DIR/$SRC_SUBDIR → $APP_DIR"
mkdir -p "$APP_DIR/data"
# копируем только подкаталог приложения, сохраняя data/ и .env
rsync -a --delete \
  --exclude 'data/' --exclude '.env' --exclude 'node_modules/' \
  "$CHECKOUT_DIR/$SRC_SUBDIR/" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Устанавливаю npm-пакеты"
sudo -u "$APP_USER" -H bash -lc "cd $APP_DIR && npm install --omit=dev"

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "==> Генерирую .env с рандомным ADMIN_TOKEN"
  TOKEN=$(openssl rand -hex 32)
  install -o "$APP_USER" -g "$APP_USER" -m 600 /dev/null "$APP_DIR/.env"
  cat > "$APP_DIR/.env" <<EOF
HOST=127.0.0.1
PORT=3000
PUBLIC_BASE_URL=
ADMIN_TOKEN=$TOKEN
DB_PATH=$APP_DIR/data/shortener.db
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "    ADMIN_TOKEN=$TOKEN"
  echo "    (сохранён в $APP_DIR/.env — отредактируйте PUBLIC_BASE_URL)"
fi

echo "==> Устанавливаю systemd-юнит"
install -m 644 "$APP_DIR/deploy/url-shortener.service" /etc/systemd/system/url-shortener.service
systemctl daemon-reload
systemctl enable --now url-shortener

sleep 1
systemctl --no-pager --full status url-shortener || true

echo
echo "Готово. Настройте Caddy/Nginx (см. deploy/Caddyfile) и откройте https://<домен>/admin"
