from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings come from environment / .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram: two bots are required ---
    # User bot: end users write here (n8n webhook). Stored for docs / future helpers.
    TELEGRAM_USER_BOT_TOKEN: str
    # Group bot: creates topics and posts into the support forum group (this service).
    TELEGRAM_GROUP_BOT_TOKEN: str
    TELEGRAM_GROUP_ID: int

    # Backward-compatible alias: if someone still has TELEGRAM_BOT_TOKEN, map it in .env
    # as TELEGRAM_GROUP_BOT_TOKEN yourself. Do not reuse one token for both bots.

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379"
    # Prefix for all Redis keys/channels used between n8n and this bot
    REDIS_KEY_PREFIX: str = "support_bot"
    TOGGLE_AI_TIMEOUT_SEC: int = 10

    # --- Support Postgres (dialogs / messages / topics) ---
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "supportbot"
    POSTGRES_USER: str = "supportbot"
    POSTGRES_PASSWORD: str

    # --- Forum topic icons (Telegram custom emoji ids) ---
    ICON_AI_ENABLED: str = "5309832892262654231"   # robot
    ICON_AI_DISABLED: str = "5350554349074391003"  # laptop

    # --- Optional product cabinet link (used in n8n card buttons) ---
    CABINET_URL: str = "https://cab.example.com"

    # --- Bedolaga / product DB (readonly for n8n user cards). Not used by this Python bot. ---
    BEDOLAGA_DB_HOST: str = ""
    BEDOLAGA_DB_PORT: int = 5432
    BEDOLAGA_DB_NAME: str = "remnawave_bot"
    BEDOLAGA_DB_USER: str = "n8n_readonly"
    BEDOLAGA_DB_PASSWORD: str = ""

    # --- n8n public URL (for webhook setup docs) ---
    N8N_HOST: str = "localhost"
    N8N_PROTOCOL: str = "http"
    WEBHOOK_URL: str = "http://localhost:5678/"

    @property
    def redis_incoming_list(self) -> str:
        return f"{self.REDIS_KEY_PREFIX}:incoming"

    @property
    def redis_messages_channel(self) -> str:
        return f"{self.REDIS_KEY_PREFIX}:messages"

    @property
    def redis_toggle_request_channel(self) -> str:
        return f"{self.REDIS_KEY_PREFIX}:toggle_request"

    def redis_toggle_response_list(self, dialog_id: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}:toggle:{dialog_id}"
