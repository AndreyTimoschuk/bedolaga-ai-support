-- Support database schema used by n8n workflows + the Telegram group bot.
-- Applied automatically on first Postgres container start.

CREATE TABLE IF NOT EXISTS dialogs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT,
    username    TEXT,
    ai_status   BOOLEAN DEFAULT TRUE,
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT,
    dialog_id   BIGINT REFERENCES dialogs(id),
    message     TEXT,
    type        TEXT,
    file_id     TEXT,
    file_type   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_topics (
    id          SERIAL PRIMARY KEY,
    dialog_id   TEXT UNIQUE NOT NULL,
    chat_id     TEXT NOT NULL,
    topic_id    INTEGER NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dialogs_user_status ON dialogs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_messages_dialog_id ON messages(dialog_id);
CREATE INDEX IF NOT EXISTS idx_chat_topics_topic_id ON chat_topics(topic_id);
