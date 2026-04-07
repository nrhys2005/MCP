import httpx

from mcp_server.config import settings

SLACK_API = "https://slack.com/api"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.slack_bot_token}",
        "Content-Type": "application/json",
    }


async def send_message(channel: str, text: str) -> dict:
    """Slack 채널에 메시지를 전송합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API}/chat.postMessage",
            headers=_headers(),
            json={"channel": channel, "text": text},
        )
        resp.raise_for_status()
        return resp.json()


async def list_channels(limit: int = 100) -> dict:
    """Slack 채널 목록을 조회합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SLACK_API}/conversations.list",
            headers=_headers(),
            params={"limit": limit, "types": "public_channel,private_channel"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_channel_history(channel: str, limit: int = 20) -> dict:
    """Slack 채널의 최근 메시지를 가져옵니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SLACK_API}/conversations.history",
            headers=_headers(),
            params={"channel": channel, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()
