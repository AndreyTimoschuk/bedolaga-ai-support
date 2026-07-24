#!/usr/bin/env bash
# Generate n8n CREDENTIALS_OVERWRITE_DATA from .env / .env.test (OpenAI + Telegram user bot).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ "$ENV_FILE" != /* ]]; then
  ENV_FILE="$ROOT/$ENV_FILE"
fi
OUT="${ROOT}/n8n/credentials-overwrite.json"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"; exit 1
fi

get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2-
}

OPENAI_API_KEY="$(get_env OPENAI_API_KEY)"
TELEGRAM_USER_BOT_TOKEN="$(get_env TELEGRAM_USER_BOT_TOKEN)"

python3 - "$OUT" "$OPENAI_API_KEY" "$TELEGRAM_USER_BOT_TOKEN" <<'PY'
import json, sys
out, openai_key, tg_token = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if openai_key and "CHANGE_ME" not in openai_key:
    data["openAiApi"] = {"apiKey": openai_key}
if tg_token and "CHANGE_ME" not in tg_token and "USER_BOT_TOKEN" not in tg_token:
    data["telegramApi"] = {"accessToken": tg_token}
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
print(f"wrote {out} ({', '.join(data.keys()) or 'empty'})")
PY
