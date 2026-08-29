#!/usr/bin/env bash
# ЄДИНИЙ спосіб деплою CRM (правило для Claude І Codex — руками build/up не робити).
#
# Порядок: збірка → міграції → СМОУК НА НОВОМУ ОБРАЗІ → і тільки якщо все
# зелене — перемикання на нову версію. Якщо смоук червоний, стара версія
# продовжує працювати, нічого не ламається.
#
# Використання:
#   ./deploy.sh          — бекенд + фронтенд (web + caddy)
#   ./deploy.sh web      — тільки бекенд
#   ./deploy.sh caddy    — тільки фронтенд (смоук все одно проганяємо)
set -euo pipefail
cd /root/gmideas/crm-platform

TARGETS="${1:-web caddy}"
C="docker compose -f docker-compose.prod.yml"

echo "== 1/4 Збірка: $TARGETS =="
# shellcheck disable=SC2086
$C build $TARGETS

echo "== 2/4 Міграції =="
$C run --rm -T web python manage.py migrate --no-input | tail -3

echo "== 3/4 Смоук нової версії (стара ще працює) =="
if ! $C run --rm -T web python smoke_all.py; then
    echo ""
    echo "ДЕПЛОЙ ЗУПИНЕНО: смоук червоний. Прод НЕ чіпали — працює стара версія."
    echo "Полагодь причину і запусти ./deploy.sh знову."
    exit 1
fi

echo "== 4/4 Перемикання на нову версію =="
$C up -d
for i in 1 2 3 4 5 6; do
    sleep 5
    code="$(curl -s -o /dev/null -w '%{http_code}' https://crm.wallcovdec.com.ua/api/privacy/ || true)"
    [ "$code" = "200" ] && break
done
echo "healthcheck HTTP=$code (спроба $i)"
if [ "$code" != "200" ]; then
    echo "УВАГА: прод не відповідає 200 після перемикання — перевір docker logs crm-platform-web-1"
    exit 1
fi
echo "DEPLOY OK $(date '+%F %T')"
