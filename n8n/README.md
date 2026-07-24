# n8n workflows

Import these JSON files into n8n after `./start.sh` (or `docker compose up`).

| File | Workflow |
|---|---|
| `support-main.json` | `PROJECT · Support Main` |
| `support-ai.json` | `PROJECT · Support AI` |
| `support-output.json` | `PROJECT · Support Output` |

## What comes from `.env` automatically

| Value | How |
|---|---|
| `OPENAI_API_KEY` | `CREDENTIALS_OVERWRITE_DATA` → all `openAiApi` credentials |
| `TELEGRAM_USER_BOT_TOKEN` | same overwrite → all `telegramApi` credentials |
| `TELEGRAM_GROUP_ID` | expression `$env.TELEGRAM_GROUP_ID` in Main filter |
| `REDIS_KEY_PREFIX` | expressions in Redis list/channel fields |
| `CABINET_URL` | expression in user-card button URL |
| `N8N_TELEGRAM_WEBHOOK_ID` | fixed UUID in Main Telegram Trigger + `scripts/set-telegram-webhook.sh` |

`start.sh` runs `scripts/gen-n8n-credentials-overwrite.sh` and writes `n8n/credentials-overwrite.json` (gitignored).

## OpenAI

1. Put key in `.env` → `OPENAI_API_KEY=sk-...`
2. Restart / start stack so overwrite file is regenerated
3. In n8n UI create credential **OpenAI**, name exactly `Shared · OpenAI`
4. Leave API Key empty (or dummy). Runtime value comes from `.env`

Same for Telegram credential `PROJECT · Support Bot`: create once, token comes from overwrite.

## Still create manually in UI

Postgres (Support + Bedolaga), Redis, Qdrant — different hosts/passwords, type-level overwrite would smash both Postgres credentials into one.

## Import order

1. Create credentials (names as in main README)
2. Import `support-output.json`
3. Import `support-ai.json`
4. Import `support-main.json`
5. Activate workflows
6. `./scripts/set-telegram-webhook.sh`

Sub-workflows are linked by **name** (`PROJECT · Support AI` / `PROJECT · Support Output`), not by REPLACE ids.

Files are also mounted at `/import/workflows` inside the n8n container.
