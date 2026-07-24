-- Idempotent stubs for e2e / local when Bedolaga credential points at Support DB.
CREATE TABLE IF NOT EXISTS n8n_users (
    id              BIGINT PRIMARY KEY,
    tg_id           BIGINT UNIQUE,
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    balance         NUMERIC DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n8n_keys (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tg_id           BIGINT,
    email           TEXT,
    tariff_name     TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    end_date        TIMESTAMPTZ,
    traffic_limit   BIGINT,
    traffic_used    BIGINT,
    device_limit    INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_n8n_users_tg_id ON n8n_users(tg_id);
CREATE INDEX IF NOT EXISTS idx_n8n_keys_tg_id ON n8n_keys(tg_id);
