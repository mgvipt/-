#!/usr/bin/env bash
# Боевой запуск GMIdeas CRM одной командой.
# Делает всё сам: ставит Docker (если нет), настраивает .env, собирает и поднимает стек.
# Запускать на сервере из каталога crm-platform/:
#   sudo bash deploy.sh
set -euo pipefail

cd "$(dirname "$0")"
echo "==> GMIdeas CRM — развёртывание"

# 1) Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Docker не найден, устанавливаю…"
  curl -fsSL https://get.docker.com | sh
fi
DC="docker compose"
$DC version >/dev/null 2>&1 || DC="docker-compose"

# 2) .env
if [ ! -f .env ]; then
  echo "==> Создаю .env"
  read -rp "Домен CRM (например crm.wallcovdec.com.ua): " DOMAIN
  DOMAIN=${DOMAIN:-crm.wallcovdec.com.ua}
  SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c32 /dev/urandom | base64)
  DBPASS=$(openssl rand -hex 16 2>/dev/null || head -c16 /dev/urandom | base64 | tr -d '/+=')
  cat > .env <<EOF
DOMAIN=$DOMAIN
SECRET_KEY=$SECRET_KEY
POSTGRES_DB=crm
POSTGRES_USER=crm
POSTGRES_PASSWORD=$DBPASS
EOF
  echo "==> .env создан (домен: $DOMAIN)"
else
  echo "==> .env уже есть — использую его"
  DOMAIN=$(grep ^DOMAIN= .env | cut -d= -f2)
fi

# 3) Сборка и запуск
echo "==> Сборка и запуск контейнеров (может занять пару минут)…"
$DC -f docker-compose.prod.yml up -d --build

echo
echo "============================================================"
echo "  Готово. Открой:  https://$DOMAIN"
echo "  (Сертификат HTTPS выпускается автоматически ~30–60 сек.)"
echo
echo "  Демо-вход:  kirill / demo12345  или  head / demo12345"
echo "  Создать своего админа:"
echo "    $DC -f docker-compose.prod.yml exec web python manage.py createsuperuser"
echo
echo "  Подключить Telegram-бота:"
echo "    $DC -f docker-compose.prod.yml exec web \\"
echo "      python manage.py telegram_channel --token ТОКЕН --name 'Wallcov бот' --domain $DOMAIN"
echo "============================================================"
