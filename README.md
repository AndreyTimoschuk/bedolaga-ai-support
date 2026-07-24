# Bedolaga AI Support

Готовый стек поддержки для проектов на [Bedolaga](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot): Telegram + n8n + AI + форум-группа для менеджеров.

Пользователь пишет в личку support-боту. n8n принимает сообщение, при необходимости зовёт AI, сохраняет диалог в своей БД и пушит событие в Redis. Group-бот из этого репозитория создаёт топик в Telegram-группе и показывает там переписку. Менеджер отвечает в топике, ответ уходит обратно пользователю.

Репозиторий: [AndreyTimoschuk/bedolaga-ai-support](https://github.com/AndreyTimoschuk/bedolaga-ai-support)

---

## Для кого это

Если у тебя уже есть Bedolaga (или похожий VPN/подписочный бот) и хочется нормальной поддержки:

- пользователи пишут в один Telegram-бот
- менеджеры сидят в одной группе с топиками
- AI отвечает первым, менеджер может перехватить
- в топике видна карточка клиента из БД Bedolaga
- кнопка открывает веб-карточку в кабинете

Это не «магическая кнопка, всё само». Docker поднимает инфраструктуру. Логику диалогов и AI ты собираешь в n8n по инструкции ниже.

---

## Как это устроено

Нужны **два разных Telegram-бота**. Один токен на всё не подойдёт: webhook и long polling конфликтуют.

1. **User bot**  
   С ним общаются клиенты. n8n вешает на него webhook.

2. **Group bot**  
   Админ в форум-группе. Этот репозиторий крутит на нём polling: создаёт топики, постит сообщения, ловит ответы менеджеров.

```text
Клиент
  └─ User bot (webhook)
       └─ n8n
            ├─ Support Postgres   (dialogs / messages)
            ├─ Bedolaga Postgres  (readonly: n8n_users / n8n_keys)
            ├─ OpenAI + Qdrant    (AI / база знаний)
            └─ Redis LPUSH {prefix}:incoming
                 └─ Group bot (этот репозиторий)
                      └─ Telegram forum group
                           └─ ответ менеджера
                                └─ Redis PUBLISH {prefix}:messages
                                     └─ n8n → User bot → клиент
```

Что происходит на практике:

1. Клиент пишет user-боту.
2. n8n находит или создаёт диалог в Support DB.
3. Если диалог новый, n8n читает карточку из Bedolaga и пушит её в Redis.
4. Group-бот создаёт топик и публикует карточку + сообщение.
5. Если AI включён, n8n генерирует ответ, шлёт клиенту и дублирует в топик.
6. Менеджер может ответить в топике или нажать «Переключить AI».
7. Иконка топика меняется: 🤖 AI on / 💻 AI off.

---

## Что поднимает Docker Compose

Одна команда поднимает весь локальный контур:

| Сервис | Контейнер | Назначение |
|---|---|---|
| `telegram-bot` | `support-telegram-bot` | Group-бот: топики, кнопки, ответы менеджеров |
| `n8n` | `support-n8n` | Автоматизация, webhook user-бота, AI |
| `postgres` | `support-postgres` | Диалоги, сообщения, dialog↔topic |
| `redis` | `support-redis` | Очередь n8n ↔ group-бот |
| `qdrant` | `support-qdrant` | Векторное хранилище для RAG |

Порты по умолчанию:

| Сервис | Порт на хосте |
|---|---|
| n8n | `5678` |
| postgres / redis / qdrant | только внутри Docker-сети `support-net` |

Из контейнера n8n ходи так:

- Postgres: host `postgres`, port `5432`
- Redis: host `redis`, port `6379`
- Qdrant: `http://qdrant:6333`

---

## Что понадобится заранее

- Docker + Docker Compose
- Два бота от [@BotFather](https://t.me/BotFather)
- Telegram-группа с включёнными Topics
- Доступ к Postgres Bedolaga (для карточки пользователя)
- Ключ OpenAI, если хочешь AI
- Для продакшена: домен и HTTPS reverse-proxy (Caddy / Nginx / Traefik)

---

## Быстрый старт

```bash
git clone https://github.com/AndreyTimoschuk/bedolaga-ai-support.git
cd bedolaga-ai-support

cp .env.example .env
nano .env   # или любой редактор
```

Минимум, без которого стек не стартует нормально:

- `TELEGRAM_USER_BOT_TOKEN`
- `TELEGRAM_GROUP_BOT_TOKEN`
- `TELEGRAM_GROUP_ID`
- `POSTGRES_PASSWORD`

Дальше:

```bash
chmod +x start.sh
./start.sh
```

Или вручную:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f telegram-bot n8n
```

Открой n8n: `http://localhost:5678`  
При первом входе n8n попросит создать owner-аккаунт. Это нормально.

Проверка, что group-бот жив:

```bash
docker compose logs telegram-bot | tail -n 30
```

Ожидай строки вроде:

```text
Database initialized (PostgreSQL)
Telegram bot started
Redis consumer started (list=support_bot:incoming)
Bot running
```

---

## Шаг 1. Два бота в BotFather

1. Создай первого бота: это **user bot**. Токен → `TELEGRAM_USER_BOT_TOKEN`.
2. Создай второго бота: это **group bot**. Токен → `TELEGRAM_GROUP_BOT_TOKEN`.
3. Убедись, что токены разные.
4. Для group-бота в BotFather можно отключить privacy mode группы, если хочешь, чтобы он видел все сообщения в топиках. Обычно для админа с polling этого достаточно, но если менеджерские ответы не ловятся, проверь privacy / права.

Почему нельзя один бот:

- n8n держит webhook на user-боте
- group-бот из этого репо делает long polling
- Telegram не даёт нормально совместить оба режима на одном токене

---

## Шаг 2. Форум-группа

1. Создай группу.
2. В настройках группы включи **Topics**.
3. Добавь **group bot** в группу.
4. Сделай его администратором.
5. Обязательно включи право **Manage Topics**.
6. Узнай id группы. Обычно это `-100...`.

Как узнать id:

- перешли любое сообщение из группы боту вроде `@userinfobot` / `@getidsbot`
- или временно залогируй update после того, как group-бот получит сообщение из группы

Пропиши id в `.env`:

```env
TELEGRAM_GROUP_ID=-100xxxxxxxxxx
```

### Иконки топиков

Telegram для forum topics принимает только специальные custom emoji id.

Список доступных для твоего group-бота:

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_GROUP_BOT_TOKEN/getForumTopicIconStickers" \
  | python3 -c 'import sys,json; [print(s["emoji"], s["custom_emoji_id"]) for s in json.load(sys.stdin)["result"]]'
```

Дефолты в `.env.example`:

| Состояние | Эмодзи | ID |
|---|---|---|
| AI включён | 🤖 | `5309832892262654231` |
| AI выключен | 💻 | `5350554349074391003` |

Если хочешь другие, поменяй `ICON_AI_ENABLED` / `ICON_AI_DISABLED` и перезапусти `telegram-bot`.

---

## Шаг 3. Файл `.env`

Все настройки только через `.env`. Скопируй `.env.example` и заполни.

### Telegram

| Переменная | Обязательно | Смысл |
|---|---|---|
| `TELEGRAM_USER_BOT_TOKEN` | да | токен бота для клиентов |
| `TELEGRAM_GROUP_BOT_TOKEN` | да | токен бота для группы |
| `TELEGRAM_GROUP_ID` | да | id форум-группы |

### Redis

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379` | URL Redis внутри compose |
| `REDIS_KEY_PREFIX` | `support_bot` | префикс всех ключей/каналов |
| `TOGGLE_AI_TIMEOUT_SEC` | `10` | сколько group-бот ждёт ответ n8n на toggle AI |

Если меняешь `REDIS_KEY_PREFIX`, поменяй те же имена ключей и в n8n.

### Support Postgres

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `POSTGRES_DB` | `supportbot` | БД диалогов |
| `POSTGRES_USER` | `supportbot` | пользователь |
| `POSTGRES_PASSWORD` | — | пароль, обязательно свой |
| `POSTGRES_HOST` | `postgres` | внутри compose |
| `POSTGRES_PORT` | `5432` | внутри compose |

### Иконки и кабинет

| Переменная | Смысл |
|---|---|
| `ICON_AI_ENABLED` | custom emoji id для AI on |
| `ICON_AI_DISABLED` | custom emoji id для AI off |
| `CABINET_URL` | база URL кабинета, для кнопки «Карточка пользователя» |

Пример кнопки: `{CABINET_URL}/admin/users/{id}`

### Bedolaga readonly DB

Эти переменные сам Python group-бот не использует. Они нужны тебе для credentials в n8n и как единый конфиг проекта.

| Переменная | Смысл |
|---|---|
| `BEDOLAGA_DB_HOST` | хост Postgres Bedolaga |
| `BEDOLAGA_DB_PORT` | порт, обычно `5432` |
| `BEDOLAGA_DB_NAME` | обычно `remnawave_bot` |
| `BEDOLAGA_DB_USER` | `n8n_readonly` |
| `BEDOLAGA_DB_PASSWORD` | пароль readonly-роли |

### OpenAI

| Переменная | Обязательно | Смысл |
|---|---|---|
| `OPENAI_API_KEY` | да, для AI | ключ OpenAI. Подставляется в n8n через credentials overwrite |

Подробно: [Шаг 6](#шаг-6-openai-api-key)

### n8n

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `N8N_HOST` | `localhost` | host заголовка n8n |
| `N8N_PORT` | `5678` | порт UI/webhook на хосте |
| `N8N_PROTOCOL` | `http` | `http` или `https` |
| `WEBHOOK_URL` | `http://localhost:5678/` | публичный URL, который увидит Telegram |
| `N8N_EDITOR_BASE_URL` | тот же | URL редактора |
| `N8N_SECURE_COOKIE` | `false` | для локального http оставь `false` |

Для продакшена:

```env
N8N_PROTOCOL=https
N8N_HOST=n8n.example.com
WEBHOOK_URL=https://n8n.example.com/
N8N_EDITOR_BASE_URL=https://n8n.example.com/
N8N_SECURE_COOKIE=true
```

---

## Шаг 4. Readonly-доступ к Bedolaga

Без этого карточка пользователя в топике не соберётся.

### 4.1. SQL на стороне Bedolaga

1. Открой `scripts/setup-bedolaga-readonly.sql`
2. Замени оба `CHANGE_ME_PASSWORD` на нормальный пароль
3. Выполни скрипт от имени владельца БД Bedolaga

```bash
docker exec -i <bedolaga_postgres_container> \
  psql -U <bedolaga_db_owner> -d remnawave_bot \
  < scripts/setup-bedolaga-readonly.sql
```

Скрипт делает:

- роль `n8n_readonly` с `default_transaction_read_only=on`
- view `public.n8n_users` — профиль, баланс, депозиты, рефералы, ограничения и т.д.
- view `public.n8n_keys` — подписки/тарифы/трафик/устройства
- schema `n8n_compat` с алиасами `users` / `keys`
- `GRANT SELECT` на нужные таблицы и views

### 4.2. Сеть

Postgres Bedolaga должен быть доступен с хоста, где крутится n8n.

Обычный вариант:

- Postgres слушает `5432`
- UFW / security group пускает только IP support-сервера

Проверка с support-хоста:

```bash
psql "postgresql://n8n_readonly:PASSWORD@BEDOLAGA_HOST:5432/remnawave_bot" \
  -c "SELECT tg_id, username, balance FROM n8n_users LIMIT 3;"
```

### 4.3. Пропиши значения в `.env`

```env
BEDOLAGA_DB_HOST=bedolaga-db.example.com
BEDOLAGA_DB_PORT=5432
BEDOLAGA_DB_NAME=remnawave_bot
BEDOLAGA_DB_USER=n8n_readonly
BEDOLAGA_DB_PASSWORD=...
CABINET_URL=https://cab.example.com
```

---

## Шаг 5. Support DB

На первом старте Postgres автоматически накатывает `scripts/init-support-db.sql`.

Таблицы:

### `dialogs`

| Поле | Смысл |
|---|---|
| `id` | id диалога |
| `user_id` | Telegram id клиента |
| `username` | username на момент создания |
| `ai_status` | `true` = AI отвечает, `false` = только менеджер |
| `status` | `active` / `closed` |
| `created_at` | когда создан |

### `messages`

История сообщений диалога: текст, тип, file_id, кто писал.

### `chat_topics`

Связка `dialog_id` ↔ `topic_id` в форум-группе. Её использует group-бот.

Если топик удалили руками в Telegram, а в БД запись осталась, group-бот будет писать в несуществующий топик. Удали строку:

```sql
DELETE FROM chat_topics WHERE dialog_id = '42';
```

Следующее входящее сообщение создаст топик заново.

---

## Шаг 6. OpenAI API key

Ключ пишешь **только** в `.env`:

```env
OPENAI_API_KEY=sk-proj-...
```

`./start.sh` (или `./scripts/gen-n8n-credentials-overwrite.sh`) собирает файл
`n8n/credentials-overwrite.json`. Compose монтирует его в n8n как
`CREDENTIALS_OVERWRITE_DATA_FILE`. n8n подставляет `apiKey` во все credentials типа OpenAI.

В UI всё равно один раз создай credential:

1. Credentials → Add → OpenAI
2. Name: `Shared · OpenAI`
3. API Key можно оставить пустым
4. Save

То же для Telegram `PROJECT · Support Bot`: токен берётся из `TELEGRAM_USER_BOT_TOKEN` через overwrite.

Если поменял ключ в `.env`:

```bash
./scripts/gen-n8n-credentials-overwrite.sh
docker compose up -d n8n
```

Postgres / Redis / Qdrant overwrite так не делаем: два Postgres credential разных, type-level overwrite затрёт оба одним набором.

---

## Шаг 7. Импорт готовых воркфлоу

Шаблоны:

```text
n8n/workflows/
├── support-main.json      → PROJECT · Support Main
├── support-ai.json        → PROJECT · Support AI
└── support-output.json    → PROJECT · Support Output
```

Коротко: [n8n/README.md](n8n/README.md)

### Что уже не REPLACE_*

| Было | Сейчас |
|---|---|
| `REPLACE_WEBHOOK_ID` | фиксированный UUID = `N8N_TELEGRAM_WEBHOOK_ID` + `scripts/set-telegram-webhook.sh` |
| `REPLACE_SUPPORT_AI_ID` / `OUTPUT` | ссылка по **имени** воркфлоу |
| group id `-100...` | `$env.TELEGRAM_GROUP_ID` |
| `support_bot:...` Redis | `$env.REDIS_KEY_PREFIX` |
| `cab.example.com` в кнопке | `$env.CABINET_URL` |
| OpenAI / Telegram secrets | overwrite из `.env` |

Credential id в JSON = имя credential. Сначала создай credentials с этими именами, потом import.

### Credentials

| Credential name | Тип | Секрет |
|---|---|---|
| `PROJECT · Support Bot` | Telegram API | из `.env` (overwrite) |
| `Shared · OpenAI` | OpenAI | из `.env` (overwrite) |
| `PROJECT · Support DB` | Postgres | host=`postgres`, db/user/pass из `.env` |
| `PROJECT · Support Redis` | Redis | host=`redis`, port=`6379` |
| `PROJECT · Bedolaga DB` | Postgres | `BEDOLAGA_DB_*` |
| `PROJECT · Qdrant` | Qdrant API | `http://qdrant:6333` |

### Import

1. Workflows → Import from File
2. `support-output.json` → `support-ai.json` → `support-main.json`
3. Activate
4. `./scripts/set-telegram-webhook.sh`

---

## Шаг 8. Первичная настройка n8n (если собираешь сам)

Если не хочешь импортировать JSON, собирай вручную. Подробный чеклист: [docs/n8n.md](docs/n8n.md)

Рекомендуемая схема из трёх воркфлоу:

1. `PROJECT · Support Main`
2. `PROJECT · Support AI`
3. `PROJECT · Support Output`

### Карточка пользователя при новом диалоге

1. `SELECT * FROM n8n_users WHERE tg_id = ...`
2. `SELECT * FROM n8n_keys WHERE tg_id = ...`
3. Собрать текст карточки
4. Кнопки:
   - `callback_data=toggle_ai:{dialog_id}:{tg_id}`
   - `url={CABINET_URL}/admin/users/{id}`

---

## Шаг 9. Webhook user-бота

Webhook id зафиксирован в шаблоне Main и в `.env` как `N8N_TELEGRAM_WEBHOOK_ID`.

После активации Main:

```bash
./scripts/set-telegram-webhook.sh
```

Скрипт ставит:

`{WEBHOOK_URL}webhook/{N8N_TELEGRAM_WEBHOOK_ID}/webhook`

Если n8n за reverse-proxy, `WEBHOOK_URL` обязан быть публичным `https://.../`.
После рестарта n8n при необходимости запусти скрипт снова.

---

## Redis-протокол

Префикс берётся из `REDIS_KEY_PREFIX`. По умолчанию `support_bot`.

| Направление | Тип | Ключ | Когда |
|---|---|---|---|
| n8n → group-бот | list | `{prefix}:incoming` | сообщение пользователя / AI / карточка |
| group-бот → n8n | pub/sub | `{prefix}:messages` | менеджер ответил в топике |
| group-бот → n8n | pub/sub | `{prefix}:toggle_request` | нажали «Переключить AI» |
| n8n → group-бот | list | `{prefix}:toggle:{dialog_id}` | ответ на toggle |

### `user_message`

```json
{
  "type": "user_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Привет",
  "ai_enabled": true,
  "file_id": null,
  "file_type": "text",
  "buttons": [
    [{"text": "Переключить AI", "callback_data": "toggle_ai:42:123456789"}],
    [{"text": "Карточка пользователя", "url": "https://cab.example.com/admin/users/1"}]
  ]
}
```

Поля медиа опциональны:

- `file_type`: `photo` / `video` / `voice` / `audio` / `document` / `sticker`
- `file_id`: Telegram `file_id` или URL файла

### `ai_response`

```json
{
  "type": "ai_response",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Сейчас проверю подписку."
}
```

### `manager_message` (из group-бота)

```json
{
  "type": "manager_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Попробуйте переподключиться",
  "from": "manager",
  "file_id": null,
  "file_type": "text"
}
```

### Toggle AI

Запрос от group-бота:

```json
{
  "type": "toggle_ai",
  "dialog_id": "42",
  "chat_id": "123456789"
}
```

Ответ n8n в list `{prefix}:toggle:42` за `TOGGLE_AI_TIMEOUT_SEC` секунд:

```json
{ "ai_enabled": false }
```

Если n8n не успел, group-бот покажет таймаут.

---

## Проверка, что всё живое

1. Напиши user-боту `/start` или любой текст.
2. В n8n должен появиться execution Main.
3. В группе должен создаться топик.
4. В топике должна быть карточка и/или сообщение пользователя.
5. Если AI включён, клиент получает ответ, а в топике появляется AI-сообщение.
6. Ответь менеджером в топике: клиент должен получить сообщение.
7. Нажми «Переключить AI»: иконка топика должна смениться.

Полезные команды:

```bash
docker compose ps
docker compose logs -f telegram-bot
docker compose logs -f n8n
docker compose restart telegram-bot n8n
```

---

## Несколько проектов на одном n8n

Если будешь поднимать поддержку для нескольких брендов:

- креды и воркфлоу именуй с префиксом: `LIBERTAS · Support Main`, `ACME · Support Bot`
- для каждого проекта свой `REDIS_KEY_PREFIX`, своя группа, свои два бота
- OpenAI можно общий: `Shared · OpenAI`
- Bedolaga DB у каждого проекта своя

Так проще не перепутать токены и Redis-ключи.

---

## Продакшен

Минимальный чеклист:

1. Домен на n8n, HTTPS через Caddy/Nginx/Traefik
2. `WEBHOOK_URL=https://n8n.example.com/`
3. `N8N_SECURE_COOKIE=true`
4. Сильные пароли в `.env`
5. UFW: Bedolaga Postgres только с IP support-хоста
6. Бэкапы volumes: `postgres_data`, `n8n_data`, при необходимости `qdrant_data`
7. Не публикуй Redis/Postgres наружу без нужды
8. Не коммить `.env`

Volumes, где лежат данные:

- `postgres_data`
- `redis_data`
- `qdrant_data`
- `n8n_data`

Остановка без удаления данных:

```bash
docker compose down
```

Полный снос данных:

```bash
docker compose down -v
```

---

## Частые проблемы

| Симптом | Что проверить |
|---|---|
| В группу ничего не приходит | Redis prefix в n8n и `.env`, логи `telegram-bot`, есть ли LPUSH в incoming |
| Топик не создаётся | group-бот админ? есть Manage Topics? верный `TELEGRAM_GROUP_ID`? |
| Webhook 403 / нет апдейтов | `getWebhookInfo`, `WEBHOOK_URL`, secret_token, переставь webhook |
| Карточка пустая / workflow падает | Bedolaga views, readonly пароль, firewall до Bedolaga DB |
| AI молчит | `dialogs.ai_status`, OpenAI credential, Qdrant, execution AI workflow |
| Ответ менеджера не доходит клиенту | Redis Trigger на `{prefix}:messages`, Output workflow, user bot token |
| `message thread not found` | удали stale row из `chat_topics` |
| getFile 401 | в HTTP Request захардкожен старый bot token |

---

## Структура репозитория

```text
bedolaga-ai-support/
├── app/
│   ├── config.py              # все настройки из .env
│   ├── database.py            # chat_topics
│   ├── n8n_client.py          # publish/toggle через Redis
│   ├── redis_consumer.py      # читает incoming
│   └── telegram_bot.py        # топики, кнопки, ответы менеджеров
├── n8n/
│   ├── README.md              # импорт воркфлоу + OpenAI credential
│   └── workflows/
│       ├── support-main.json
│       ├── support-ai.json
│       └── support-output.json
├── tests/                     # contract + e2e pytest
├── scripts/
│   ├── init-support-db.sql
│   ├── setup-bedolaga-readonly.sql
│   ├── e2e-bootstrap.sh
│   ├── run-tests.sh           # one-shot: up → pytest → down
│   ├── n8n-import-workflows.py
│   ├── gen-n8n-credentials-overwrite.sh
│   └── set-telegram-webhook.sh
├── test.sh                    # → scripts/run-tests.sh
├── docs/
│   └── n8n.md
├── docker-compose.yml
├── docker-compose.test.yml
├── .env.example
├── .env.test.example
├── start.sh
└── README.md
```

---

## Тесты (contract + e2e)

Два слоя:

1. `contract` — redis + postgres + group-бот. `LPUSH` в `{prefix}:incoming`, проверка Redis outbox и топика в группе.
2. `e2e` — полный стек + cloudflared + n8n. Webhook Update (текст/фото) и manager через Redis `messages`.

### Подготовка

```bash
cp .env.test.example .env.test
# Заполни:
#   TELEGRAM_USER_BOT_TOKEN   — user/webhook бот
#   TELEGRAM_GROUP_BOT_TOKEN  — group/polling бот (другой!)
#   TELEGRAM_GROUP_ID         — форум-группа с Topics
#   TEST_USER_CHAT_ID         — твой Telegram user id (/start у user-бота + ты в группе)

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

./scripts/e2e-bootstrap.sh
```

Bootstrap поднимает compose, пишет credentials overwrite, ждёт cloudflared URL, импортирует воркфлоу в n8n и ставит webhook.

В `TEST_MODE=1` group-бот после успешной отправки пишет событие в `{REDIS_KEY_PREFIX}:test:outbox`.

### Запуск

Одним скриптом (поднять стек → pytest → снести контейнеры):

```bash
./test.sh
# или
./scripts/run-tests.sh
```

Оставить стек после прогона:

```bash
KEEP_STACK=1 ./test.sh
```

Вручную:

```bash
./scripts/e2e-bootstrap.sh
.venv/bin/pytest tests/ -m contract -q
.venv/bin/pytest tests/ -m e2e -q
```

Секреты только в `.env.test` (файл в `.gitignore`). В git не коммить.

---

## Чего в репозитории пока нет

- автозагрузки knowledge base в Qdrant
- готового reverse-proxy
- автосоздания самих credential-записей в UI без bootstrap-скрипта

Инфраструктура, group-бот, шаблоны воркфлоу и e2e-тесты уже в репо.

---

## Лицензия

MIT. Используй, меняй, распространяй. Сохрани копирайт. Без гарантий.
