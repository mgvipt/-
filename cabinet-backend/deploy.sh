#!/usr/bin/env bash
# Развернуть «Кабинет» (синхронизация) на сервере. Запускать НА сервере из папки cabinet-backend.
#   bash deploy.sh
# API будет доступно через Nginx калькулятора: https://calc.wallcovdec.com.ua/api/ и /auth/
set -euo pipefail

CONTAINER="wallcov-cabinet"
PORT=8090
DATA_DIR="/var/www/wallcov-cabinet-data"   # данные (db.json) хранятся вне контейнера

if [ ! -f .env ] || ! grep -q '^JWT_SECRET=' .env; then
  [ -f .env ] || cp .env.example .env
  echo "❌ Заполните .env (JWT_SECRET и SIGNUP_CODE), затем запустите снова: nano .env && bash deploy.sh"; exit 1
fi

mkdir -p "${DATA_DIR}"
echo "==> Docker build"
docker build -t "${CONTAINER}" .
echo "==> Перезапуск контейнера (данные в ${DATA_DIR})"
docker rm -f "${CONTAINER}" 2>/dev/null || true
docker run -d --name "${CONTAINER}" --restart unless-stopped \
  --env-file .env -v "${DATA_DIR}:/app/data" -p 127.0.0.1:${PORT}:${PORT} "${CONTAINER}"
sleep 2
curl -fsS "http://localhost:${PORT}/health" && echo " ✅ кабинет работает"
echo ""
echo "Теперь обнови Nginx калькулятора, чтобы появился /api:  cd .. && bash deploy-calculator.sh"
