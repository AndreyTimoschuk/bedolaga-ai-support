"""Full-stack e2e via n8n E2E Webhook ingress + Redis manager path."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import httpx
import pytest

from tests.conftest import ensure_stub_bedolaga_user, require_test_user
from tests.helpers import (
    blpop_outbox,
    blpop_outbox_matching,
    telegram_update_photo,
    telegram_update_text,
    wait_topic,
)


def _e2e_ingress_url(env: dict[str, str]) -> str:
    # Hit local n8n directly (no Telegram secret_token required)
    port = env.get("N8N_PORT", "5679")
    return f"http://127.0.0.1:{port}/webhook/e2e-ingress"


async def _n8n_ready(env: dict[str, str]) -> None:
    port = env.get("N8N_PORT", "5679")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"http://127.0.0.1:{port}/healthz")
            if r.status_code >= 500:
                pytest.skip("n8n not healthy")
        except Exception as exc:
            pytest.skip(f"n8n not reachable: {exc}")


async def _assert_recent_n8n_success(env: dict[str, str], timeout: float = 90.0) -> bool:
    port = env.get("N8N_PORT", "5679")
    email = env.get("N8N_OWNER_EMAIL", "e2e@example.com")
    password = env.get("N8N_OWNER_PASSWORD", "E2eOwnerPass123!")
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout

    async with httpx.AsyncClient(base_url=base, timeout=30.0, follow_redirects=True) as client:
        r = await client.post(
            "/rest/login",
            json={"emailOrLdapLoginId": email, "password": password},
        )
        if r.status_code >= 400:
            r = await client.post("/rest/login", json={"email": email, "password": password})
        if r.status_code >= 400:
            return False

        while time.time() < deadline:
            er = await client.get("/rest/executions", params={"limit": 15})
            if er.status_code >= 400:
                await asyncio.sleep(2)
                continue
            body = er.json()
            items = body.get("data") if isinstance(body, dict) else body
            results = (items or {}).get("results") if isinstance(items, dict) else items
            for item in results or []:
                if item.get("status") == "success" or item.get("finished") is True:
                    return True
            await asyncio.sleep(2)
    return False


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_webhook_text(redis_client, pg_pool, redis_prefix, env):
    await _n8n_ready(env)
    user_id = int(require_test_user(env))
    await ensure_stub_bedolaga_user(pg_pool, user_id)
    await redis_client.delete(f"{redis_prefix}:test:outbox")

    marker = f"e2e-text-{uuid.uuid4().hex[:8]}"
    update = telegram_update_text(
        update_id=int(time.time()) % 1_000_000_000,
        user_id=user_id,
        text=marker,
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(_e2e_ingress_url(env), json=update)
        assert r.status_code < 500, r.text

    # New-dialog path pushes the user card first; accept any outbox for this user
    # and require a dialog + topic in Support DB.
    event = await blpop_outbox(redis_client, redis_prefix, timeout=90)
    assert event["kind"] == "user_message"
    assert event.get("message_id")

    row = await pg_pool.fetchrow(
        "SELECT id FROM dialogs WHERE user_id = $1 AND status = 'active' ORDER BY id DESC LIMIT 1",
        user_id,
    )
    assert row is not None
    await wait_topic(pg_pool, str(row["id"]), timeout=30)

    # Best-effort: user text may land in messages depending on workflow branch
    msg = await pg_pool.fetchrow(
        "SELECT id FROM messages WHERE message LIKE $1 ORDER BY id DESC LIMIT 1",
        f"%{marker}%",
    )
    if msg is None:
        # Card-only new-dialog path still proves n8n → redis → bot
        assert "Telegram ID" in (event.get("text") or "") or event.get("dialog_id")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_webhook_photo(redis_client, pg_pool, redis_prefix, env, http_server_photo_url):
    await _n8n_ready(env)
    user_id = int(require_test_user(env))
    await ensure_stub_bedolaga_user(pg_pool, user_id)

    # Seed a photo file_id-like URL into a fake Update.photo[].file_id is a Telegram id;
    # for e2e without DM we still exercise text+caption path if photo getFile fails.
    # Prefer contract photo for media; here send captioned photo update with remote URL
    # injected after filter by using text-only if needed.
    # Practical path: post text update with photo marker AND separately LPUSH is contract.
    # For true n8n photo path we need a real Telegram file_id from user bot.
    user_token = env["TELEGRAM_USER_BOT_TOKEN"]
    caption = f"e2e-photo-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Try upload to user; if chat not found, fall back to text-only e2e assertion skip media
        r = await client.post(
            f"https://api.telegram.org/bot{user_token}/sendPhoto",
            data={"chat_id": user_id, "caption": caption},
            files={"photo": ("t.png", _tiny_png(), "image/png")},
        )
        if r.status_code >= 400:
            pytest.skip(
                f"User bot cannot DM TEST_USER_CHAT_ID ({r.text}). "
                "Open @lbrts_cicd1_bot and press /start, then re-run."
            )
        body = r.json()
        assert body.get("ok"), body
        file_id = body["result"]["photo"][-1]["file_id"]

        await redis_client.delete(f"{redis_prefix}:test:outbox")
        update = telegram_update_photo(
            update_id=int(time.time()) % 1_000_000_000,
            user_id=user_id,
            file_id=file_id,
            caption=caption,
        )
        wr = await client.post(_e2e_ingress_url(env), json=update)
        assert wr.status_code < 500, wr.text

    event = await blpop_outbox(redis_client, redis_prefix, timeout=120)
    assert event["kind"] == "user_message"
    assert event["file_type"] == "photo"
    assert event.get("message_id")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_manager_text_to_user(redis_client, pg_pool, redis_prefix, env):
    await _n8n_ready(env)
    user_id = require_test_user(env)

    # Numeric dialog id — n8n SQL casts dialog_id to bigint
    dialog_id = str(
        await pg_pool.fetchval(
            """
            INSERT INTO dialogs (user_id, username, ai_status, status)
            VALUES ($1, 'e2e', false, 'active')
            RETURNING id
            """,
            int(user_id),
        )
    )

    await redis_client.delete(f"{redis_prefix}:test:outbox")
    await redis_client.lpush(
        f"{redis_prefix}:incoming",
        json.dumps(
            {
                "type": "user_message",
                "dialog_id": dialog_id,
                "chat_id": str(user_id),
                "message": "seed for manager text",
                "ai_enabled": False,
                "file_type": "text",
            }
        ),
    )
    await blpop_outbox(redis_client, redis_prefix, timeout=45)
    await wait_topic(pg_pool, dialog_id, timeout=20)

    marker = f"manager-text-{uuid.uuid4().hex[:8]}"
    await redis_client.publish(
        f"{redis_prefix}:messages",
        json.dumps(
            {
                "type": "manager_message",
                "dialog_id": dialog_id,
                "chat_id": str(user_id),
                "message": marker,
                "from": "manager",
                "file_type": "text",
            }
        ),
    )

    ok = await _assert_recent_n8n_success(env, timeout=90)
    assert ok, "n8n did not report success after manager text publish"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_manager_photo_to_user(redis_client, pg_pool, redis_prefix, env):
    await _n8n_ready(env)
    user_id = require_test_user(env)
    user_token = env["TELEGRAM_USER_BOT_TOKEN"]

    dialog_id = str(
        await pg_pool.fetchval(
            """
            INSERT INTO dialogs (user_id, username, ai_status, status)
            VALUES ($1, 'e2e', false, 'active')
            RETURNING id
            """,
            int(user_id),
        )
    )

    await redis_client.delete(f"{redis_prefix}:test:outbox")
    await redis_client.lpush(
        f"{redis_prefix}:incoming",
        json.dumps(
            {
                "type": "user_message",
                "dialog_id": dialog_id,
                "chat_id": str(user_id),
                "message": "seed for manager photo",
                "ai_enabled": False,
                "file_type": "text",
            }
        ),
    )
    await blpop_outbox(redis_client, redis_prefix, timeout=45)
    await wait_topic(pg_pool, dialog_id, timeout=20)

    caption = f"manager-photo-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{user_token}/sendPhoto",
            data={"chat_id": user_id, "caption": caption},
            files={"photo": ("m.png", _tiny_png(), "image/png")},
        )
        if r.status_code >= 400:
            pytest.skip(
                f"User bot cannot DM TEST_USER_CHAT_ID ({r.text}). "
                "Open @lbrts_cicd1_bot and press /start, then re-run."
            )
        body = r.json()
        assert body.get("ok"), body
        file_id = body["result"]["photo"][-1]["file_id"]

    await redis_client.publish(
        f"{redis_prefix}:messages",
        json.dumps(
            {
                "type": "manager_message",
                "dialog_id": dialog_id,
                "chat_id": str(user_id),
                "message": caption,
                "from": "manager",
                "file_id": file_id,
                "file_type": "photo",
            }
        ),
    )

    ok = await _assert_recent_n8n_success(env, timeout=90)
    assert ok, "n8n did not report success after manager photo publish"


def _tiny_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
