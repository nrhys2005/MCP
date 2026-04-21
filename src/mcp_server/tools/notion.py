import re
import uuid

import httpx

from mcp_server.config import settings

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
_MAX_RICH_TEXT_LENGTH = 2000

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=NOTION_API,
            headers={
                "Authorization": f"Bearer {settings.notion_api_key}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
    return _client


def _normalize_id(raw_id: str) -> str:
    """하이픈 없는 32자 hex ID를 UUID 형식으로 변환합니다."""
    cleaned = raw_id.replace("-", "")
    if len(cleaned) == 32:
        try:
            return str(uuid.UUID(cleaned))
        except ValueError:
            pass
    return raw_id


async def search(query: str, filter_type: str | None = None, page_size: int = 10) -> dict:
    """Notion에서 페이지/데이터베이스를 검색합니다."""
    body: dict = {"query": query, "page_size": page_size}
    if filter_type in ("page", "database"):
        body["filter"] = {"value": filter_type, "property": "object"}
    resp = await _get_client().post("/search", json=body)
    resp.raise_for_status()
    return resp.json()


async def get_page(page_id: str) -> dict:
    """Notion 페이지 정보를 조회합니다."""
    page_id = _normalize_id(page_id)
    resp = await _get_client().get(f"/pages/{page_id}")
    resp.raise_for_status()
    return resp.json()


async def create_page(parent: dict, properties: dict, children: list | None = None) -> dict:
    """Notion 페이지를 생성합니다."""
    for key in ("page_id", "database_id"):
        if key in parent:
            parent[key] = _normalize_id(parent[key])
    body: dict = {"parent": parent, "properties": properties}
    if children:
        body["children"] = children
    resp = await _get_client().post("/pages", json=body)
    resp.raise_for_status()
    return resp.json()


async def update_page(page_id: str, properties: dict) -> dict:
    """Notion 페이지 속성을 수정합니다."""
    page_id = _normalize_id(page_id)
    resp = await _get_client().patch(f"/pages/{page_id}", json={"properties": properties})
    resp.raise_for_status()
    return resp.json()


async def get_database(database_id: str) -> dict:
    """Notion 데이터베이스 정보를 조회합니다."""
    database_id = _normalize_id(database_id)
    resp = await _get_client().get(f"/databases/{database_id}")
    resp.raise_for_status()
    return resp.json()


async def query_database(
    database_id: str, filter_by: dict | None = None, sorts: list | None = None, page_size: int = 10,
) -> dict:
    """Notion 데이터베이스를 쿼리합니다."""
    database_id = _normalize_id(database_id)
    all_results: list = []
    cursor: str | None = None
    while len(all_results) < page_size:
        current_batch_size = min(page_size - len(all_results), 100)
        body: dict = {"page_size": current_batch_size}
        if filter_by:
            body["filter"] = filter_by
        if sorts:
            body["sorts"] = sorts
        if cursor:
            body["start_cursor"] = cursor
        resp = await _get_client().post(f"/databases/{database_id}/query", json=body)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return {"results": all_results[:page_size], "has_more": False, "next_cursor": None}


async def get_block_children(block_id: str, page_size: int = 100) -> dict:
    """Notion 블록의 하위 블록(페이지 콘텐츠)을 모두 조회합니다. (cursor 자동 페이지네이션)"""
    block_id = _normalize_id(block_id)
    all_results: list = []
    cursor: str | None = None
    request_page_size = min(page_size, 100)
    while True:
        params: dict = {"page_size": request_page_size}
        if cursor:
            params["start_cursor"] = cursor
        resp = await _get_client().get(f"/blocks/{block_id}/children", params=params)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return {"results": all_results, "has_more": False, "next_cursor": None}


async def append_block_children(block_id: str, children: list) -> dict:
    """Notion 블록에 하위 블록(콘텐츠)을 추가합니다."""
    block_id = _normalize_id(block_id)
    resp = await _get_client().patch(f"/blocks/{block_id}/children", json={"children": children})
    resp.raise_for_status()
    return resp.json()


def _parse_inline(text: str) -> list[dict]:
    """마크다운 인라인 서식(bold, italic, code, strikethrough, link)을 Notion rich_text 배열로 변환합니다."""
    rich_text: list[dict] = []
    pattern = re.compile(
        r"(?P<bold_italic>\*\*\*(.+?)\*\*\*)"
        r"|(?P<bold>\*\*(.+?)\*\*)"
        r"|(?P<italic>\*(.+?)\*)"
        r"|(?P<strike>~~(.+?)~~)"
        r"|(?P<code>`(.+?)`)"
        r"|(?P<link>\[([^\]]+)\]\(([^)]+)\))"
    )
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            rich_text.append({"type": "text", "text": {"content": text[pos : m.start()]}})
        if m.group("bold_italic"):
            content = m.group(2)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"bold": True, "italic": True},
            })
        elif m.group("bold"):
            content = m.group(4)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"bold": True},
            })
        elif m.group("italic"):
            content = m.group(6)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"italic": True},
            })
        elif m.group("strike"):
            content = m.group(8)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"strikethrough": True},
            })
        elif m.group("code"):
            content = m.group(10)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"code": True},
            })
        elif m.group("link"):
            link_text = m.group(12)
            link_url = m.group(13)
            rich_text.append({
                "type": "text",
                "text": {"content": link_text, "link": {"url": link_url}},
            })
        pos = m.end()
    if pos < len(text):
        rich_text.append({"type": "text", "text": {"content": text[pos:]}})
    return rich_text or [{"type": "text", "text": {"content": text}}]


def _split_rich_text(rich_text: list[dict]) -> list[list[dict]]:
    """Notion API 2000자 제한에 맞춰 rich_text 배열을 분할합니다."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0
    for rt in rich_text:
        content = rt["text"]["content"]
        if current_len + len(content) <= _MAX_RICH_TEXT_LENGTH:
            current.append(rt)
            current_len += len(content)
        else:
            remaining = content
            while remaining:
                space = _MAX_RICH_TEXT_LENGTH - current_len
                if space <= 0:
                    chunks.append(current)
                    current = []
                    current_len = 0
                    space = _MAX_RICH_TEXT_LENGTH
                piece = remaining[:space]
                remaining = remaining[space:]
                new_rt = {**rt, "text": {**rt["text"], "content": piece}}
                current.append(new_rt)
                current_len += len(piece)
    if current:
        chunks.append(current)
    return chunks or [[{"type": "text", "text": {"content": ""}}]]


def _make_block(block_type: str, rich_text: list[dict], **extra: object) -> list[dict]:
    """블록 타입과 rich_text로 Notion 블록을 생성합니다. 2000자 초과 시 여러 블록으로 분할합니다."""
    blocks = []
    for chunk in _split_rich_text(rich_text):
        body = {"rich_text": chunk, **extra}
        blocks.append({"object": "block", "type": block_type, block_type: body})
    return blocks


def parse_markdown_to_blocks(text: str) -> list[dict]:
    """마크다운 텍스트를 Notion 블록 리스트로 변환합니다.

    지원하는 블록 타입:
    - heading_1 / heading_2 / heading_3
    - bulleted_list_item / numbered_list_item
    - to_do (체크박스)
    - code (코드 블록)
    - quote (인용)
    - divider (구분선)
    - table (마크다운 테이블)
    - paragraph (기본)
    - 인라인: bold, italic, strikethrough, code, link
    """
    blocks: list[dict] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # 코드 블록
        code_match = re.match(r"^```(\w*)", line)
        if code_match:
            language = code_match.group(1) or "plain text"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # skip closing ```
            code_content = "\n".join(code_lines)
            rich_text = [{"type": "text", "text": {"content": code_content}}]
            blocks.extend(_make_block("code", rich_text, language=language))
            continue

        # 마크다운 테이블 (헤더 행 + 구분선 행이 있어야 테이블로 인식)
        table_match = re.match(r"^\|(.+)\|$", line)
        if table_match and i + 1 < len(lines) and re.match(r"^\|[-:\s|]+\|$", lines[i + 1]):
            # 헤더 행 파싱
            header_cells = [c.strip() for c in table_match.group(1).split("|")]
            table_rows = [header_cells]
            i += 2  # 헤더 행 + 구분선 행 건너뛰기
            # 데이터 행 파싱
            while i < len(lines):
                row_match = re.match(r"^\|(.+)\|$", lines[i])
                if not row_match:
                    break
                cells = [c.strip() for c in row_match.group(1).split("|")]
                table_rows.append(cells)
                i += 1
            # Notion table 블록 생성
            table_width = len(header_cells)
            table_children = []
            for row in table_rows:
                padded = row[:table_width] + [""] * max(0, table_width - len(row))
                cells = [_parse_inline(cell) for cell in padded]
                table_children.append({
                    "object": "block",
                    "type": "table_row",
                    "table_row": {"cells": cells},
                })
            blocks.append({
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": table_width,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": table_children,
                },
            })
            continue

        # 구분선
        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", line):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # 헤딩
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            content = heading_match.group(2)
            block_type = f"heading_{level}"
            blocks.extend(_make_block(block_type, _parse_inline(content)))
            i += 1
            continue

        # 체크박스
        todo_match = re.match(r"^[-*]\s+\[([ xX])\]\s+(.+)$", line)
        if todo_match:
            checked = todo_match.group(1) in ("x", "X")
            content = todo_match.group(2)
            blocks.extend(_make_block("to_do", _parse_inline(content), checked=checked))
            i += 1
            continue

        # 불릿 리스트
        bullet_match = re.match(r"^[-*+]\s+(.+)$", line)
        if bullet_match:
            content = bullet_match.group(1)
            blocks.extend(_make_block("bulleted_list_item", _parse_inline(content)))
            i += 1
            continue

        # 숫자 리스트
        numbered_match = re.match(r"^\d+\.\s+(.+)$", line)
        if numbered_match:
            content = numbered_match.group(1)
            blocks.extend(_make_block("numbered_list_item", _parse_inline(content)))
            i += 1
            continue

        # 인용
        quote_match = re.match(r"^>\s*(.*)$", line)
        if quote_match:
            content = quote_match.group(1)
            blocks.extend(_make_block("quote", _parse_inline(content)))
            i += 1
            continue

        # 빈 줄 무시
        if not line.strip():
            i += 1
            continue

        # 기본 paragraph
        blocks.extend(_make_block("paragraph", _parse_inline(line)))
        i += 1

    return blocks


def build_paragraph_blocks(text: str) -> list[dict]:
    """마크다운 텍스트를 Notion 블록 리스트로 변환합니다. (하위 호환)"""
    return parse_markdown_to_blocks(text)
