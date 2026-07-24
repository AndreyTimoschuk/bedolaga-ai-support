import json
import redis.asyncio as aioredis
from app.config import Settings


class N8NClient:
    """Redis client used to talk to n8n"""

    def __init__(self, settings: Settings, redis: aioredis.Redis):
        self.settings = settings
        self.redis = redis

    async def send_manager_message(
        self,
        dialog_id: str,
        chat_id: str,
        message: str,
        file_id: str = None,
        file_type: str = None,
    ) -> bool:
        try:
            payload = {
                "type": "manager_message",
                "dialog_id": dialog_id,
                "chat_id": chat_id,
                "message": message,
                "from": "manager",
            }
            if file_id:
                payload["file_id"] = file_id
            if file_type:
                payload["file_type"] = file_type
            await self.redis.publish(
                self.settings.redis_messages_channel,
                json.dumps(payload),
            )
            return True
        except Exception as e:
            print(f"Error sending to Redis: {e}")
            return False

    async def toggle_ai_status(self, dialog_id: str, chat_id: str) -> dict:
        print(f"Toggle AI for dialog_id: {dialog_id}")
        try:
            await self.redis.publish(
                self.settings.redis_toggle_request_channel,
                json.dumps(
                    {
                        "type": "toggle_ai",
                        "dialog_id": dialog_id,
                        "chat_id": chat_id,
                    }
                ),
            )

            result = await self.redis.blpop(
                self.settings.redis_toggle_response_list(dialog_id),
                timeout=self.settings.TOGGLE_AI_TIMEOUT_SEC,
            )

            if not result:
                return {
                    "error": (
                        f"Timeout: n8n did not answer within "
                        f"{self.settings.TOGGLE_AI_TIMEOUT_SEC} seconds"
                    )
                }

            data = json.loads(result[1])

            if "ai_enabled" not in data:
                return {"error": "n8n response missing 'ai_enabled'"}

            if not isinstance(data["ai_enabled"], bool):
                return {"error": "Invalid ai_enabled type from n8n"}

            print(f"AI toggled: {data['ai_enabled']}")
            return {"ai_enabled": data["ai_enabled"]}

        except Exception as e:
            print(f"Unexpected error: {e}")
            return {"error": f"{type(e).__name__}: {str(e)}"}
