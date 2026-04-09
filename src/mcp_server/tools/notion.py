import httpx

from mcp_server.config import settings

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
_MAX_RICH_TEXT_LENGTH = 2000


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.notion_api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def search(query: str, filter_type: str | None = None, page_size: int = 10) -> dict:
    """Notion에서 페이지/데이터베이스를 검색합니다."""
    body: dict = {"query": query, "page_size": page_size}
    if filter_type in ("page", "database"):
        body["filter"] = {"value": filter_type, "property": "object"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{NOTION_API}/search", headers=_headers(), json=body)
        resp.raise_for_status()
        return resp.json()


async def get_page(page_id: str) -> dict:
    """Notion 페이지 정보를 조회합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{NOTION_API}/pages/{page_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def create_page(parent: dict, properties: dict, children: list | None = None) -> dict:
    """Notion 페이지를 생성합니다."""
    body: dict = {"parent": parent, "properties": properties}
    if children:
        body["children"] = children
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{NOTION_API}/pages", headers=_headers(), json=body)
        resp.raise_for_status()
        return resp.json()


async def update_page(page_id: str, properties: dict) -> dict:
    """Notion 페이지 속성을 수정합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{NOTION_API}/pages/{page_id}", headers=_headers(), json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()


async def get_database(database_id: str) -> dict:
    """Notion 데이터베이스 정보를 조회합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{NOTION_API}/databases/{database_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def query_database(
    database_id: str, filter_by: dict | None = None, sorts: list | None = None, page_size: int = 10,
) -> dict:
    """Notion 데이터베이스를 쿼리합니다."""
    body: dict = {"page_size": page_size}
    if filter_by:
        body["filter"] = filter_by
    if sorts:
        body["sorts"] = sorts
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{NOTION_API}/databases/{database_id}/query", headers=_headers(), json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def get_block_children(block_id: str, page_size: int = 100) -> dict:
    """Notion 블록의 하위 블록(페이지 콘텐츠)을 조회합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{NOTION_API}/blocks/{block_id}/children",
            headers=_headers(),
            params={"page_size": page_size},
        )
        resp.raise_for_status()
        return resp.json()


async def append_block_children(block_id: str, children: list) -> dict:
    """Notion 블록에 하위 블록(콘텐츠)을 추가합니다."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{NOTION_API}/blocks/{block_id}/children",
            headers=_headers(),
            json={"children": children},
        )
        resp.raise_for_status()
        return resp.json()


def build_paragraph_blocks(text: str) -> list[dict]:
    """긴 텍스트를 Notion API 2000자 제한에 맞춰 paragraph 블록 리스트로 변환합니다."""
    blocks = []
    for i in range(0, len(text), _MAX_RICH_TEXT_LENGTH):
        chunk = text[i : i + _MAX_RICH_TEXT_LENGTH]
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
            },
        })
    return blocks
