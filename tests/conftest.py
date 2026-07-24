from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg
import httpx
import pytest
import redis.asyncio as aioredis

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> dict[str, str]:
    env_path = path or ROOT / ".env.test"
    if not env_path.exists():
        pytest.skip(f"Missing {env_path}")
    data: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    for k, v in os.environ.items():
        if k.startswith(
            ("TELEGRAM_", "TEST_", "REDIS_", "POSTGRES_", "N8N_", "WEBHOOK_", "OPENAI_")
        ):
            data[k] = v
    return data


@pytest.fixture(scope="session")
def env() -> dict[str, str]:
    return load_env()


@pytest.fixture(scope="session")
def redis_prefix(env: dict[str, str]) -> str:
    return env.get("REDIS_KEY_PREFIX", "support_bot_test")


@pytest.fixture
async def redis_client(env: dict[str, str]):
    port = env.get("TEST_REDIS_PORT", "6380")
    url = f"redis://127.0.0.1:{port}/0"
    client = aioredis.from_url(url, decode_responses=True, socket_timeout=120)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.skip(f"Redis not reachable at {url}: {exc}")
    yield client
    await client.aclose()


@pytest.fixture
async def pg_pool(env: dict[str, str]):
    port = int(env.get("TEST_POSTGRES_PORT", "5433"))
    try:
        pool = await asyncpg.create_pool(
            host="127.0.0.1",
            port=port,
            user=env.get("POSTGRES_USER", "supportbot"),
            password=env.get("POSTGRES_PASSWORD", "supportbot"),
            database=env.get("POSTGRES_DB", "supportbot"),
            min_size=1,
            max_size=2,
        )
    except Exception as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    yield pool
    await pool.close()


@pytest.fixture
def unique_dialog_id() -> str:
    import uuid

    return f"e2e-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def http_server_photo_url() -> str:
    # Served by photo-fixture container on the compose network
    return "http://photo-fixture:8080/pixel.jpg"


def require_test_user(env: dict[str, str]) -> str:
    chat_id = env.get("TEST_USER_CHAT_ID", "")
    if not chat_id or "CHANGE_ME" in chat_id:
        pytest.skip(
            "Set TEST_USER_CHAT_ID in .env.test (real user who /start'ed the user bot)"
        )
    return str(chat_id)


async def ensure_stub_bedolaga_user(pg_pool, tg_id: int | str) -> None:
    tid = int(tg_id)
    await pg_pool.execute(
        """
        INSERT INTO n8n_users (id, tg_id, username, first_name)
        VALUES ($1, $1, 'e2e_user', 'E2E')
        ON CONFLICT (tg_id) DO NOTHING
        """,
        tid,
    )
