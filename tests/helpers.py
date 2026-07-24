from __future__ import annotations

import json
import time
from typing import Any

import asyncpg


async def blpop_outbox(redis_client, prefix: str, timeout: int = 30) -> dict:
    key = f"{prefix}:test:outbox"
    result = await redis_client.blpop(key, timeout=timeout)
    if not result:
        raise AssertionError(f"No outbox event on {key} within {timeout}s")
    return json.loads(result[1])


async def blpop_outbox_matching(
    redis_client,
    prefix: str,
    *,
    timeout: int = 90,
    text_contains: str | None = None,
    file_type: str | None = None,
) -> dict:
    """Pop outbox events until one matches (skips user-card noise)."""
    import time

    deadline = time.time() + timeout
    key = f"{prefix}:test:outbox"
    while time.time() < deadline:
        remaining = max(1, int(deadline - time.time()))
        result = await redis_client.blpop(key, timeout=min(remaining, 10))
        if not result:
            continue
        event = json.loads(result[1])
        if text_contains and text_contains not in (event.get("text") or ""):
            continue
        if file_type and event.get("file_type") != file_type:
            continue
        return event
    raise AssertionError(
        f"No matching outbox event on {key} within {timeout}s "
        f"(text_contains={text_contains!r}, file_type={file_type!r})"
    )


async def wait_topic(pg_pool: asyncpg.Pool, dialog_id: str, timeout: float = 30.0) -> dict:
    import asyncio

    deadline = time.time() + timeout
    while time.time() < deadline:
        row = await pg_pool.fetchrow(
            "SELECT dialog_id, chat_id, topic_id FROM chat_topics WHERE dialog_id = $1",
            str(dialog_id),
        )
        if row:
            return dict(row)
        await asyncio.sleep(0.5)
    raise AssertionError(f"chat_topics row missing for dialog_id={dialog_id}")


def telegram_update_text(*, update_id: int, user_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "text": text,
            "chat": {"id": user_id, "type": "private", "first_name": "E2E"},
            "from": {"id": user_id, "is_bot": False, "first_name": "E2E"},
        },
    }


def telegram_update_photo(
    *,
    update_id: int,
    user_id: int,
    file_id: str,
    caption: str = "",
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "message_id": update_id,
        "date": int(time.time()),
        "chat": {"id": user_id, "type": "private", "first_name": "E2E"},
        "from": {"id": user_id, "is_bot": False, "first_name": "E2E"},
        "photo": [
            {
                "file_id": file_id,
                "file_unique_id": f"uq{update_id}",
                "width": 100,
                "height": 100,
                "file_size": 100,
            },
            {
                "file_id": file_id,
                "file_unique_id": f"uq{update_id}b",
                "width": 320,
                "height": 320,
                "file_size": 1000,
            },
        ],
    }
    if caption:
        msg["caption"] = caption
    return {"update_id": update_id, "message": msg}
