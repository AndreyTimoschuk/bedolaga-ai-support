# Настройка n8n под этот стек

## 1. Credentials

Из контейнера n8n:

| Имя | Тип | Host / URL |
|---|---|---|
| Support Bot | Telegram | токен `TELEGRAM_USER_BOT_TOKEN` |
| Support DB | Postgres | `postgres:5432`, db/user/pass из `.env` |
| Support Redis | Redis | `redis:6379` |
| Bedolaga DB | Postgres | `BEDOLAGA_DB_*` из `.env` |
| Qdrant | Qdrant API | `http://qdrant:6333` |
| OpenAI | OpenAI | свой ключ |

## 2. Три воркфлоу (рекомендуемая схема)

Имена с префиксом проекта, если проектов несколько:

1. `PROJECT · Support Main`
   - Telegram Trigger (user bot)
   - фильтр: игнор сообщений из `TELEGRAM_GROUP_ID`
   - поиск/создание диалога в Support DB
   - запись сообщения
   - Redis LPUSH в `{REDIS_KEY_PREFIX}:incoming`
   - если AI включён → Execute Workflow AI
2. `PROJECT · Support AI`
   - LLM + Qdrant
   - ответ пользователю через Output
   - Redis LPUSH `type=ai_response` в incoming (чтобы AI-ответ был виден в топике)
3. `PROJECT · Support Output`
   - отправка текста/фото/стикера user-боту

Дополнительно в Main:
- Redis Trigger на `{REDIS_KEY_PREFIX}:messages` → ответ менеджера пользователю
- Redis Trigger на `{REDIS_KEY_PREFIX}:toggle_request` → flip `dialogs.ai_status` → LPUSH в `{REDIS_KEY_PREFIX}:toggle:{dialog_id}`

## 3. Карточка пользователя

При создании нового диалога:
1. SELECT из `n8n_users` по `tg_id`
2. SELECT из `n8n_keys` по `tg_id`
3. Собрать текст карточки
4. Кнопки:
   - `callback_data=toggle_ai:{dialog_id}:{tg_id}`
   - url=`{CABINET_URL}/admin/users/{id}`

## 4. Webhook после рестарта n8n

n8n иногда требует переустановки webhook. Храни `WEBHOOK_URL` и secret в `.env`/доке и переставляй webhook после рестарта, если Telegram начал отдавать 403/не доставляет апдейты.

## 5. Частые грабли

- Один токен на user+group бота → сломанный webhook/polling
- Group bot без Manage Topics → топики не создаются
- Redis prefix в n8n и в `.env` различаются → тишина в группе
- В HTTP Request захардкожен старый bot token → 401 на getFile
- Bedolaga view не создан / UFW закрыт → карточка падает, первый ответ может не уйти
