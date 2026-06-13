#!/usr/bin/env bash
# Развернуть ВСЁ на Hetzner: калькулятор (статический) + AI-бэкенд (Docker).
# Запускать НА сервере из папки репозитория:  bash deploy-all.sh
set -euo pipefail

echo "════════ 1/2 · КАЛЬКУЛЯТОР (calc.wallcovdec.com.ua) ════════"
bash deploy-calculator.sh

echo ""
echo "════════ 2/2 · AI-БЭКЕНД (ai.wallcovdec.com.ua) ════════"
cd ai-backend
if [ ! -f .env ] || ! grep -q '^ANTHROPIC_API_KEY=sk-' .env 2>/dev/null; then
  [ -f .env ] || cp .env.example .env
  echo "⏸  AI-бэкенд пропущен: заполните ключи и запустите его отдельно:"
  echo "    nano ai-backend/.env      # ANTHROPIC_API_KEY=sk-ant-...  и  API_TOKEN=..."
  echo "    cd ai-backend && bash deploy.sh"
else
  bash deploy.sh
fi

echo ""
echo "✅ Готово. Калькулятор: https://calc.wallcovdec.com.ua"
