# Bedolaga AI Support

Стек поддержки для VPN/подписочного бота на базе [Bedolaga](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot) + n8n + Telegram forum topics.

Пользователь пишет в личку support-боту → n8n → AI / менеджер → ответ.
Менеджеры работают в Telegram-группе: каждый диалог = отдельный топик.

Репозиторий: [AndreyTimoschuk/bedolaga-ai-support](https://github.com/AndreyTimoschuk/bedolaga-ai-support)

---

## Что поднимается одной командой

`docker compose up` поднимает:

| Сервис | Зачем |
|---|---|
| `telegram-bot` | Group-бот: топики, сообщения менеджеров, кнопка AI |
| `n8n` | Автоматизация, AI, webhook user-бота |
| `postgres` | Диалоги / сообщения / связка dialog↔topic |
| `redis` | Очередь между n8n и group-ботом |
| `qdrant` | Векторная база для AI (RAG) |

---

## Важно про двух ботов

Нужны **два разных** бота от @BotFather:

1. **User bot** — пользователи пишут сюда. n8n ставит на него webhook.
2. **Group bot** — админ в форум-группе с правом Manage Topics. Этот репозиторий крутит на нём long polling.

Один токен на оба режима использовать нельзя: webhook и polling конфликтуют.

---

## Быстрый старт

```bash
git clone https://github.com/AndreyTimoschuk/bedolaga-ai-support.git
cd bedolaga-ai-support

cp .env.example .env
# заполни .env (минимум: оба токена, TELEGRAM_GROUP_ID, POSTGRES_PASSWORD)

chmod +x start.sh
./start.sh
```

Или вручную:

```bash
docker compose up -d --build
docker compose logs -f telegram-bot n8n
```

n8n откроется на `http://localhost:5678` (или на `WEBHOOK_URL` из `.env`).

---

## Telegram: группа

1. Создай группу, включи Topics.
2. Добавь **group bot** админом.
3. Выдай право **Manage Topics**.
4. Узнай id группы (`-100...`) и пропиши в `TELEGRAM_GROUP_ID`.

Список доступных иконок топиков:

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_GROUP_BOT_TOKEN/getForumTopicIconStickers" \
  | python3 -c 'import sys,json; [print(s["emoji"], s["custom_emoji_id"]) for s in json.load(sys.stdin)["result"]]'
```

По умолчанию:
- AI включён: 🤖 `5309832892262654231`
- AI выключен: 💻 `5350554349074391003`

---

## Настройка Bedolaga DB (карточка пользователя)

Чтобы в топике показывалась карточка клиента из Bedolaga, на **сервере Bedolaga** создай readonly-роль и views.

1. Открой `scripts/setup-bedolaga-readonly.sql`
2. Замени `CHANGE_ME_PASSWORD` на нормальный пароль
3. Выполни SQL от имени владельца БД Bedolaga, например:

```bash
# пример: контейнер и пользователь зависят от твоей установки Bedolaga
docker exec -i <bedolaga_postgres_container> \
  psql -U <bedolaga_db_owner> -d remnawave_bot \
  < scripts/setup-bedolaga-readonly.sql
```

Скрипт создаёт:
- роль `n8n_readonly` (только чтение)
- views `n8n_users` / `n8n_keys`
- schema `n8n_compat` (алиасы `users` / `keys`)

4. Открой Postgres Bedolaga для IP сервера поддержки (UFW/security group), порт `5432`
5. Пропиши в `.env`:

```env
BEDOLAGA_DB_HOST=...
BEDOLAGA_DB_PORT=5432
BEDOLAGA_DB_NAME=remnawave_bot
BEDOLAGA_DB_USER=n8n_readonly
BEDOLAGA_DB_PASSWORD=...
CABINET_URL=https://cab.your-domain.com
```

6. В n8n создай credential Postgres на эти данные и читай таблицы `n8n_users` / `n8n_keys`

---

## Настройка n8n (после первого запуска)

### Credentials

Создай в UI (имена лучше с префиксом проекта, если проектов несколько):

| Credential | Тип | Куда |
|---|---|---|
| `PROJECT · Support Bot` | Telegram API | `TELEGRAM_USER_BOT_TOKEN` |
| `PROJECT · Support DB` | Postgres | host=`postgres`, db/user/pass из `.env` |
| `PROJECT · Support Redis` | Redis | host=`redis`, port=`6379` |
| `PROJECT · Bedolaga DB` | Postgres | `BEDOLAGA_DB_*` |
| `Shared · OpenAI` | OpenAI | твой ключ |
| `PROJECT · Qdrant` | Qdrant API | `http://qdrant:6333` |

Из контейнера n8n хосты такие: `postgres`, `redis`, `qdrant`.

### Webhook user-бота

В Telegram Trigger укажи user bot credential.
После активации workflow поставь webhook:

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_USER_BOT_TOKEN}/setWebhook" \
  -d "url=${WEBHOOK_URL}webhook/<WEBHOOK_ID>/webhook" \
  -d "allowed_updates=[\"message\"]"
```

`WEBHOOK_ID` возьми из ноды Telegram Trigger в n8n.
Если n8n за reverse-proxy, `WEBHOOK_URL` должен быть публичным https.

### Redis-протокол (уже вынесен в `.env`)

Префикс задаётся `REDIS_KEY_PREFIX` (по умолчанию `support_bot`).

| Направление | Тип | Ключ |
|---|---|---|
| n8n → bot | list | `{prefix}:incoming` |
| bot → n8n | pub/sub | `{prefix}:messages` |
| bot → n8n | pub/sub | `{prefix}:toggle_request` |
| n8n → bot | list | `{prefix}:toggle:{dialog_id}` |

Пример `user_message` в `{prefix}:incoming`:

```json
{
  "type": "user_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Привет",
  "ai_enabled": true,
  "buttons": [
    [{"text": "Переключить AI", "callback_data": "toggle_ai:42:123456789"}],
    [{"text": "Карточка пользователя", "url": "https://cab.example.com/admin/users/1"}]
  ]
}
```

Ответ на toggle (в течение `TOGGLE_AI_TIMEOUT_SEC` секунд):

```json
{ "ai_enabled": false }
```

Подробный чеклист воркфлоу: [docs/n8n.md](docs/n8n.md)

---

## Переменные `.env`

Все настройки живут в `.env`. Скопируй из `.env.example`.

Обязательно:
- `TELEGRAM_USER_BOT_TOKEN`
- `TELEGRAM_GROUP_BOT_TOKEN`
- `TELEGRAM_GROUP_ID`
- `POSTGRES_PASSWORD`

Остальное имеет дефолты. Не хардкодь токены в HTTP-нодах n8n, если можно обойтись credentials / expressions из env.

---

## Схема БД поддержки

На первом старте Postgres накатывает `scripts/init-support-db.sql`:

- `dialogs` — диалоги и флаг AI
- `messages` — история
- `chat_topics` — связь `dialog_id` ↔ `topic_id`

Если топик удалили в Telegram вручную, удали строку из `chat_topics`. Следующее сообщение создаст топик заново.

---

## Архитектура

```text
User
  └─ User bot (webhook)
       └─ n8n
            ├─ Support DB (postgres)
            ├─ Bedolaga DB readonly (n8n_users / n8n_keys)
            ├─ OpenAI + Qdrant
            └─ Redis {prefix}:incoming
                 └─ Group bot (this repo)
                      └─ Forum group topics
                           └─ manager reply → Redis {prefix}:messages → n8n → User bot
```

---

## Операции

```bash
docker compose ps
docker compose logs -f telegram-bot
docker compose restart telegram-bot n8n
docker compose down
```

Данные лежат в Docker volumes: `postgres_data`, `redis_data`, `qdrant_data`, `n8n_data`.

---

## Безопасность

- Не коммить `.env`
- User bot и group bot — разные токены
- Bedolaga readonly: отдельный пользователь, только SELECT, лучше `default_transaction_read_only=on`
- Postgres Bedolaga наружу только с IP n8n/support-хоста
- Для продакшена поставь n8n за https (Caddy/Nginx) и нормальный `WEBHOOK_URL`

---

## Структура репозитория

```text
bedolaga-ai-support/
├── app/                         # group-бот
├── scripts/
│   ├── init-support-db.sql      # схема support postgres
│   └── setup-bedolaga-readonly.sql
├── docs/n8n.md
├── docker-compose.yml           # bot + n8n + redis + postgres + qdrant
├── .env.example
├── start.sh
└── README.md
```

---

## Лицензия

MIT. Коротко: делай что хочешь, сохрани копирайт, без гарантий.
