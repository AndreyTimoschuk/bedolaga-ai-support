#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
  echo "Fill both Telegram tokens, TELEGRAM_GROUP_ID, POSTGRES_PASSWORD, OPENAI_API_KEY, then run again."
  exit 1
fi

get_env() {
  local key="$1"
  grep -E "^${key}=" .env | tail -n1 | cut -d= -f2-
}

USER_TOKEN="$(get_env TELEGRAM_USER_BOT_TOKEN)"
GROUP_TOKEN="$(get_env TELEGRAM_GROUP_BOT_TOKEN)"
GROUP_ID="$(get_env TELEGRAM_GROUP_ID)"
PG_PASS="$(get_env POSTGRES_PASSWORD)"
WEBHOOK_URL="$(get_env WEBHOOK_URL)"
OPENAI_KEY="$(get_env OPENAI_API_KEY)"

if [[ -z "$USER_TOKEN" || "$USER_TOKEN" == *"USER_BOT_TOKEN"* ]]; then
  echo "Set TELEGRAM_USER_BOT_TOKEN in .env"; exit 1
fi
if [[ -z "$GROUP_TOKEN" || "$GROUP_TOKEN" == *"GROUP_BOT_TOKEN"* ]]; then
  echo "Set TELEGRAM_GROUP_BOT_TOKEN in .env"; exit 1
fi
if [[ -z "$GROUP_ID" || "$GROUP_ID" == "-1001234567890" ]]; then
  echo "Set TELEGRAM_GROUP_ID in .env"; exit 1
fi
if [[ -z "$PG_PASS" || "$PG_PASS" == *"change_me"* ]]; then
  echo "Set POSTGRES_PASSWORD in .env"; exit 1
fi
if [[ "$USER_TOKEN" == "$GROUP_TOKEN" ]]; then
  echo "User bot and group bot must use different tokens."; exit 1
fi
if [[ -z "$OPENAI_KEY" || "$OPENAI_KEY" == *"CHANGE_ME"* ]]; then
  echo "Warning: OPENAI_API_KEY empty — AI workflow will fail until you set it."
fi

chmod +x scripts/*.sh 2>/dev/null || true
./scripts/gen-n8n-credentials-overwrite.sh

docker compose up -d --build
echo
echo "n8n:  ${WEBHOOK_URL:-http://localhost:5678/}"
echo "logs: docker compose logs -f telegram-bot n8n"
echo "next: create n8n credentials (OpenAI/Telegram fields come from .env overwrite),"
echo "      import n8n/workflows/*.json, then: ./scripts/set-telegram-webhook.sh"
