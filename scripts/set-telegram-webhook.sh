#!/usr/bin/env bash
# Point Telegram user-bot webhook at n8n Telegram Trigger.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]]; then
  if [[ -f .env.test ]]; then ENV_FILE=.env.test
  elif [[ -f .env ]]; then ENV_FILE=.env
  else
    echo "Missing .env / .env.test"; exit 1
  fi
fi

get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2-
}

TOKEN="${TELEGRAM_USER_BOT_TOKEN:-$(get_env TELEGRAM_USER_BOT_TOKEN)}"
BASE="${WEBHOOK_URL:-$(get_env WEBHOOK_URL)}"
WID="${N8N_TELEGRAM_WEBHOOK_ID:-$(get_env N8N_TELEGRAM_WEBHOOK_ID)}"
WID="${WID:-a1b2c3d4-e5f6-7890-abcd-ef1234567890}"

if [[ -z "$TOKEN" || "$TOKEN" == *"CHANGE_ME"* || "$TOKEN" == *"USER_BOT_TOKEN"* ]]; then
  echo "Set TELEGRAM_USER_BOT_TOKEN"; exit 1
fi
if [[ -z "$BASE" ]]; then
  echo "Set WEBHOOK_URL"; exit 1
fi

[[ "$BASE" == */ ]] || BASE="${BASE}/"
URL="${BASE}webhook/${WID}/webhook"

echo "setWebhook -> $URL"
curl -sS -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -d "url=${URL}" \
  -d 'allowed_updates=["message"]'
echo
curl -sS "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
echo
