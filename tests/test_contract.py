"""Contract tests: LPUSH into Redis incoming, assert group-bot outbox + topic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import blpop_outbox, wait_topic

FIXTURE_JPG = Path(__file__).resolve().parent / "fixtures" / "pixel.jpg"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_contract_text_to_topic(
    redis_client,
    pg_pool,
    redis_prefix,
    unique_dialog_id,
    env,
):
    chat_id = env.get("TEST_USER_CHAT_ID") or "999001"
    if "CHANGE_ME" in str(chat_id):
        chat_id = "999001"

    await redis_client.delete(f"{redis_prefix}:test:outbox")

    payload = {
        "type": "user_message",
        "dialog_id": unique_dialog_id,
        "chat_id": str(chat_id),
        "message": f"contract text {unique_dialog_id}",
        "ai_enabled": False,
        "file_type": "text",
    }
    await redis_client.lpush(f"{redis_prefix}:incoming", json.dumps(payload))

    event = await blpop_outbox(redis_client, redis_prefix, timeout=45)
    assert event["kind"] == "user_message"
    assert event["dialog_id"] == unique_dialog_id
    assert event["file_type"] == "text"
    assert "contract text" in event["text"]
    assert event.get("message_id")

    topic = await wait_topic(pg_pool, unique_dialog_id, timeout=15)
    assert topic["topic_id"] > 0


@pytest.mark.contract
@pytest.mark.asyncio
async def test_contract_photo_to_topic(
    redis_client,
    pg_pool,
    redis_prefix,
    unique_dialog_id,
    env,
    http_server_photo_url,
):
    chat_id = env.get("TEST_USER_CHAT_ID") or "999002"
    if "CHANGE_ME" in str(chat_id):
        chat_id = "999002"

    await redis_client.delete(f"{redis_prefix}:test:outbox")

    payload = {
        "type": "user_message",
        "dialog_id": unique_dialog_id,
        "chat_id": str(chat_id),
        "message": f"contract photo {unique_dialog_id}",
        "ai_enabled": False,
        "file_id": http_server_photo_url,
        "file_type": "photo",
    }
    await redis_client.lpush(f"{redis_prefix}:incoming", json.dumps(payload))

    event = await blpop_outbox(redis_client, redis_prefix, timeout=60)
    assert event["kind"] == "user_message"
    assert event["dialog_id"] == unique_dialog_id
    assert event["file_type"] == "photo"
    assert event.get("message_id")

    topic = await wait_topic(pg_pool, unique_dialog_id, timeout=15)
    assert topic["topic_id"] > 0
