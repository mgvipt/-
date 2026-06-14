#!/usr/bin/env bash
# Развёртывание Wallcov AI backend на сервере (запускать НА Hetzner, в папке ai-backend).
# Использование:  bash deploy.sh
set -euo pipefail

DOMAIN="${DOMAIN:-ai.wallcovdec.com.ua}"
WHISPER_MODEL_NAME="${WHISPER_MODEL_NAME:-small}"   # small (быстро) | medium (точнее, тяжелее)
CONTAINER="wallcov-ai"
PORT="${PORT:-8099}"   # 8080 і 8091 на цьому сервері зайняті; беремо вільний (перевірте ss -ltn)

echo "==> Проверка .env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "❌ Создан .env из шаблона. Впишите ANTHROPIC_API_KEY и API_TOKEN, затем запустите снова:"
  echo "   nano .env && bash deploy.sh"
  exit 1
fi
if ! grep -q '^ANTHROPIC_API_KEY=sk-' .env; then
  echo "❌ В .env не заполнен ANTHROPIC_API_KEY (sk-ant-...). Впишите и запустите снова."; exit 1
fi

echo "==> Docker build (whisper.cpp + модель ${WHISPER_MODEL_NAME}) — может занять несколько минут"
docker build --build-arg WHISPER_MODEL_NAME="${WHISPER_MODEL_NAME}" -t "${CONTAINER}" .

echo "==> Перезапуск контейнера"
docker rm -f "${CONTAINER}" 2>/dev/null || true
docker run -d --name "${CONTAINER}" --restart unless-stopped \
  --env-file .env -e PORT="${PORT}" -p 127.0.0.1:${PORT}:${PORT} "${CONTAINER}"

sleep 2
echo "==> Health-check"
curl -fsS "http://localhost:${PORT}/health" && echo " ✅ контейнер работает"

echo "==> Nginx конфиг для ${DOMAIN}"
NGINX_FILE="/etc/nginx/sites-available/${DOMAIN}"
cat > "${NGINX_FILE}" <<NGINX
server {
  server_name ${DOMAIN};
  client_max_body_size 250M;
  location / {
    proxy_pass http://127.0.0.1:${PORT};
    proxy_read_timeout 600s;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
  }
}
NGINX
ln -sf "${NGINX_FILE}" "/etc/nginx/sites-enabled/${DOMAIN}"
nginx -t && systemctl reload nginx

echo "==> SSL (Let's Encrypt). Если домен уже указывает на этот сервер — выдаст сертификат."
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "admin@${DOMAIN#ai.}" || \
  echo "⚠️ certbot не отработал автоматически — запустите вручную: certbot --nginx -d ${DOMAIN}"

echo ""
echo "✅ Готово. Проверка снаружи:"
echo "   curl -X POST https://${DOMAIN}/process -H 'Authorization: Bearer <API_TOKEN из .env>' -F roomName=Тест -F video=@test.mp4"
