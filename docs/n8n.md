# Настройка n8n под этот стек

## 0. OpenAI / Telegram из `.env`

`OPENAI_API_KEY` и `TELEGRAM_USER_BOT_TOKEN` из `.env` попадают в n8n через `CREDENTIALS_OVERWRITE_DATA_FILE`.

`./start.sh` вызывает `scripts/gen-n8n-credentials-overwrite.sh` и пишет `n8n/credentials-overwrite.json`.

В UI один раз создай credentials с нужными именами. Поля apiKey / accessToken можно оставить пустыми: runtime возьмёт значения из overwrite.

## 1. Credentials

| Имя | Тип | Откуда секрет / host |
|---|---|---|
| `Shared · OpenAI` | OpenAI | `OPENAI_API_KEY` (overwrite) |
| `PROJECT · Support Bot` | Telegram | `TELEGRAM_USER_BOT_TOKEN` (overwrite) |
| `PROJECT · Support DB` | Postgres | host=`postgres`, db/user/pass из `.env` |
| `PROJECT · Support Redis` | Redis | host=`redis`, port=`6379` |
| `PROJECT · Bedolaga DB` | Postgres | `BEDOLAGA_DB_*` из `.env` |
| `PROJECT · Qdrant` | Qdrant API | `http://qdrant:6333` |

## 2. Env внутри workflow expressions

В контейнер n8n прокинуты:

- `TELEGRAM_GROUP_ID`
- `REDIS_KEY_PREFIX`
- `CABINET_URL`
- `OPENAI_API_KEY`
- `TELEGRAM_USER_BOT_TOKEN`

Шаблоны воркфлоу читают group id, redis prefix и cabinet URL через `$env.*`. Sub-workflow ссылки — по имени воркфлоу.

Webhook id Telegram Trigger зафиксирован:

`N8N_TELEGRAM_WEBHOOK_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890`

После импорта:

```bash
./scripts/set-telegram-webhook.sh
```

## 3. Импорт

- `n8n/workflows/support-output.json`
- `n8n/workflows/support-ai.json`
- `n8n/workflows/support-main.json`

Порядок: Output → AI → Main.

## 4. Карточка пользователя

При новом диалоге:
1. SELECT из `n8n_users` по `tg_id`
2. SELECT из `n8n_keys` по `tg_id`
3. Кнопки toggle AI + url из `CABINET_URL`

## 5. Частые грабли

- Пустой `OPENAI_API_KEY` / не пересобрали overwrite → AI падает
- Не создан credential `Shared · OpenAI` (даже пустой) → нода без credential
- Redis prefix в `.env` и в group-боте разные → тишина в группе
- Не вызвали `set-telegram-webhook.sh` → Telegram не бьёт в n8n
- Bedolaga view / UFW → карточка падает
