#!/usr/bin/env bash
# Bootstrap full e2e stack: compose + credentials overwrite + n8n import + tunnel webhook.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.test}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file "$ENV_FILE")
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-support-e2e}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy .env.test.example and fill tokens + TEST_USER_CHAT_ID"
  exit 1
fi

# Base compose references .env; keep it in sync for test runs
if [[ "$ENV_FILE" != ".env" ]]; then
  ln -sfn "$(basename "$ENV_FILE")" .env
fi

get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2-
}

USER_TOKEN="$(get_env TELEGRAM_USER_BOT_TOKEN)"
GROUP_TOKEN="$(get_env TELEGRAM_GROUP_BOT_TOKEN)"
GROUP_ID="$(get_env TELEGRAM_GROUP_ID)"
PG_PASS="$(get_env POSTGRES_PASSWORD)"
N8N_PORT="$(get_env N8N_PORT)"
N8N_PORT="${N8N_PORT:-5679}"
WEBHOOK_ID="$(get_env N8N_TELEGRAM_WEBHOOK_ID)"
WEBHOOK_ID="${WEBHOOK_ID:-a1b2c3d4-e5f6-7890-abcd-ef1234567890}"

if [[ -z "$USER_TOKEN" || "$USER_TOKEN" == *"CHANGE_ME"* ]]; then
  echo "Set TELEGRAM_USER_BOT_TOKEN in $ENV_FILE"; exit 1
fi
if [[ -z "$GROUP_TOKEN" || "$GROUP_TOKEN" == *"CHANGE_ME"* ]]; then
  echo "Set TELEGRAM_GROUP_BOT_TOKEN in $ENV_FILE"; exit 1
fi
if [[ "$USER_TOKEN" == "$GROUP_TOKEN" ]]; then
  echo "User and group bots must differ"; exit 1
fi
if [[ -z "$PG_PASS" ]]; then
  echo "Set POSTGRES_PASSWORD in $ENV_FILE"; exit 1
fi

chmod +x scripts/*.sh 2>/dev/null || true

# credentials overwrite from test env
ENV_FILE="$ENV_FILE" ./scripts/gen-n8n-credentials-overwrite.sh
# ensure file exists for compose mount
if [[ ! -f n8n/credentials-overwrite.json ]]; then
  cp n8n/credentials-overwrite.example.json n8n/credentials-overwrite.json
fi

echo "==> Starting compose ($COMPOSE_PROJECT_NAME)"
"${COMPOSE[@]}" up -d --build

echo "==> Waiting for postgres"
for i in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "$(get_env POSTGRES_USER)" -d "$(get_env POSTGRES_DB)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Ensuring e2e stub schema (n8n_users / n8n_keys)"
"${COMPOSE[@]}" exec -T postgres \
  psql -U "$(get_env POSTGRES_USER)" -d "$(get_env POSTGRES_DB)" \
  < scripts/ensure-e2e-schema.sql >/dev/null

echo "==> Waiting for n8n on :${N8N_PORT}"
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:${N8N_PORT}/healthz" >/dev/null 2>&1 \
    || curl -sf "http://127.0.0.1:${N8N_PORT}/healthz/readiness" >/dev/null 2>&1 \
    || curl -sf "http://127.0.0.1:${N8N_PORT}/" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Waiting for cloudflared public URL"
TUNNEL_URL=""
for i in $(seq 1 60); do
  TUNNEL_URL="$("${COMPOSE[@]}" logs cloudflared 2>&1 | grep -Eo 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' | tail -n1 || true)"
  if [[ -n "$TUNNEL_URL" ]]; then
    break
  fi
  sleep 2
done

if [[ -z "$TUNNEL_URL" ]]; then
  echo "WARNING: cloudflared URL not found; webhook stays on localhost (e2e webhook tests need public URL)"
  PUBLIC_WEBHOOK_URL="http://127.0.0.1:${N8N_PORT}/"
else
  PUBLIC_WEBHOOK_URL="${TUNNEL_URL}/"
  echo "Tunnel: $TUNNEL_URL"
  # Persist into .env.test for pytest / setWebhook
  if grep -q '^WEBHOOK_URL=' "$ENV_FILE"; then
    sed -i.bak "s|^WEBHOOK_URL=.*|WEBHOOK_URL=${PUBLIC_WEBHOOK_URL}|" "$ENV_FILE"
    rm -f "${ENV_FILE}.bak"
  else
    echo "WEBHOOK_URL=${PUBLIC_WEBHOOK_URL}" >> "$ENV_FILE"
  fi
  if grep -q '^N8N_EDITOR_BASE_URL=' "$ENV_FILE"; then
    sed -i.bak "s|^N8N_EDITOR_BASE_URL=.*|N8N_EDITOR_BASE_URL=${PUBLIC_WEBHOOK_URL}|" "$ENV_FILE"
    rm -f "${ENV_FILE}.bak"
  fi
  # Recreate n8n with public WEBHOOK_URL
  WEBHOOK_URL="$PUBLIC_WEBHOOK_URL" N8N_EDITOR_BASE_URL="$PUBLIC_WEBHOOK_URL" N8N_PROTOCOL=https \
    "${COMPOSE[@]}" up -d n8n
  sleep 5
fi

echo "==> Importing n8n workflows + credentials"
PYTHON=python3
if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
elif [[ -x .venv/bin/python3 ]]; then
  PYTHON=.venv/bin/python3
fi
if ! "$PYTHON" -c "import httpx" 2>/dev/null; then
  echo "httpx missing — run: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
  exit 1
fi
"$PYTHON" scripts/n8n-import-workflows.py --env-file "$ENV_FILE" --base-url "http://127.0.0.1:${N8N_PORT}"

# Do NOT overwrite Telegram webhook here.
# n8n Telegram Trigger registers webhook + secret_token on Main activate.

echo
echo "Bootstrap done."
echo "  n8n:      http://127.0.0.1:${N8N_PORT}/"
echo "  e2e POST: http://127.0.0.1:${N8N_PORT}/webhook/e2e-ingress"
echo "  tunnel:   ${PUBLIC_WEBHOOK_URL}"
echo "  pytest:   .venv/bin/pytest tests/ -m contract -q"
echo "            .venv/bin/pytest tests/ -m e2e -q"
echo "  note: open @user-bot and /start once so DM photo tests work"
