#!/usr/bin/env bash
# Размещение калькулятора (decorator.html) на вашем Hetzner как статического сайта.
# Запускать НА сервере, из папки репозитория (где лежит decorator.html).
#   bash deploy-calculator.sh
set -euo pipefail

DOMAIN="${DOMAIN:-calc.wallcovdec.com.ua}"
WEBROOT="/var/www/wallcov-calc"

if [ ! -f decorator.html ]; then
  echo "❌ Запускайте из папки репозитория, где есть decorator.html"; exit 1
fi

echo "==> Копирую калькулятор в ${WEBROOT}"
mkdir -p "${WEBROOT}"
cp decorator.html "${WEBROOT}/index.html"

echo "==> Nginx для ${DOMAIN}"
NGINX_FILE="/etc/nginx/sites-available/${DOMAIN}"
cat > "${NGINX_FILE}" <<NGINX
server {
  server_name ${DOMAIN};
  root ${WEBROOT};
  index index.html;
  client_max_body_size 25M;
  location /api/  { proxy_pass http://127.0.0.1:8090/api/;  proxy_set_header Host \$host; proxy_read_timeout 120s; }
  location /auth/ { proxy_pass http://127.0.0.1:8090/auth/; proxy_set_header Host \$host; }
  location /ai/   { proxy_pass http://127.0.0.1:8091/; proxy_set_header Host \$host; client_max_body_size 350M; proxy_read_timeout 600s; }
  location /      { add_header Cache-Control "no-store" always; try_files \$uri /index.html; }
}
NGINX
ln -sf "${NGINX_FILE}" "/etc/nginx/sites-enabled/${DOMAIN}"
nginx -t && systemctl reload nginx

echo "==> SSL (Let's Encrypt)"
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "admin@${DOMAIN#calc.}" || \
  echo "⚠️ certbot не отработал автоматически — запустите: certbot --nginx -d ${DOMAIN}"

echo ""
echo "✅ Готово: https://${DOMAIN}"
echo "Чтобы обновить калькулятор после изменений: git pull && bash deploy-calculator.sh"
