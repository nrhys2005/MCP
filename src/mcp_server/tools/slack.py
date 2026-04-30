import httpx

from mcp_server.config import settings

SLACK_API = "https://slack.com/api"

_client: httpx.AsyncClient | None = None
_DEFAULT_TIMEOUT = 30.0


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {settings.slack_bot_token}",
                "Content-Type": "application/json",
            },
            timeout=_DEFAULT_TIMEOUT,
        )
    return _client


def _check_response(data: dict) -> dict:
    """Slack API는 HTTP 200이라도 ok=false일 수 있으므로 확인합니다."""
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
    return data


async def send_message(channel: str, text: str) -> dict:
    """Slack 채널에 메시지를 전송합니다."""
    client = _get_client()
    resp = await client.post(
        f"{SLACK_API}/chat.postMessage",
        json={"channel": channel, "text": text},
    )
    resp.raise_for_status()
    return _check_response(resp.json())


async def list_channels(limit: int = 100) -> dict:
    """Slack 채널 목록을 조회합니다."""
    client = _get_client()
    resp = await client.get(
        f"{SLACK_API}/conversations.list",
        params={"limit": limit, "types": "public_channel,private_channel"},
    )
    resp.raise_for_status()
    return _check_response(resp.json())


async def get_channel_history(channel: str, limit: int = 20) -> dict:
    """Slack 채널의 최근 메시지를 가져옵니다."""
    client = _get_client()
    resp = await client.get(
        f"{SLACK_API}/conversations.history",
        params={"channel": channel, "limit": limit},
    )
    resp.raise_for_status()
    return _check_response(resp.json())
