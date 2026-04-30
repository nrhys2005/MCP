import base64
import re
from pathlib import Path

import httpx

from mcp_server.config import settings

_client: httpx.AsyncClient | None = None
_DEFAULT_TIMEOUT = 30.0


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        credentials = base64.b64encode(
            f"{settings.jira_email}:{settings.jira_api_token}".encode()
        ).decode()
        _client = httpx.AsyncClient(
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            timeout=_DEFAULT_TIMEOUT,
        )
    return _client


def _markdown_to_adf(text: str) -> dict:
    """마크다운 텍스트를 Atlassian Document Format(ADF)으로 변환합니다."""
    content = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # 빈 줄 스킵
        if not line.strip():
            i += 1
            continue

        # 헤딩 (## heading)
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            content.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": [{"type": "text", "text": heading_match.group(2)}],
            })
            i += 1
            continue

        # 테이블 (| col1 | col2 |)
        if line.strip().startswith("|"):
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row_text = lines[i].strip()
                # 구분선 (|---|---| ) 스킵
                if re.match(r"^\|[\s\-:|]+\|$", row_text):
                    i += 1
                    continue
                cells = [
                    c.strip() for c in row_text.strip("|").split("|")
                ]
                is_header = len(table_rows) == 0
                row_cells = []
                for cell in cells:
                    cell_type = "tableHeader" if is_header else "tableCell"
                    row_cells.append({
                        "type": cell_type,
                        "content": [{
                            "type": "paragraph",
                            "content": _parse_inline(cell),
                        }],
                    })
                table_rows.append({"type": "tableRow", "content": row_cells})
                i += 1
            if table_rows:
                content.append({"type": "table", "content": table_rows})
            continue

        # 리스트 항목 (- item 또는 * item)
        if re.match(r"^[\-\*]\s+", line):
            list_items = []
            while i < len(lines) and re.match(r"^[\-\*]\s+", lines[i]):
                item_text = re.sub(r"^[\-\*]\s+", "", lines[i])
                list_items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": _parse_inline(item_text),
                    }],
                })
                i += 1
            content.append({"type": "bulletList", "content": list_items})
            continue

        # 코드 블록 (``` 또는 {code})
        if line.strip().startswith("```"):
            language = line.strip().removeprefix("```").strip() or None
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # ``` 닫기 스킵
            attrs = {}
            if language:
                attrs["language"] = language
            content.append({
                "type": "codeBlock",
                "attrs": attrs,
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            })
            continue

        # Jira 위키 코드 블록 ({code} 또는 {noformat})
        wiki_code_match = re.match(r"^\{(code|noformat)\}$", line.strip())
        if wiki_code_match:
            code_lines = []
            i += 1
            while i < len(lines) and not re.match(
                r"^\{(code|noformat)\}$", lines[i].strip()
            ):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # {code} 닫기 스킵
            content.append({
                "type": "codeBlock",
                "attrs": {},
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            })
            continue

        # 일반 텍스트 (paragraph)
        content.append({
            "type": "paragraph",
            "content": _parse_inline(line),
        })
        i += 1

    return {"type": "doc", "version": 1, "content": content}


def _parse_inline(text: str) -> list[dict]:
    """인라인 마크다운(**bold**, `code` 등)을 ADF 인라인 노드로 변환합니다."""
    nodes = []
    pattern = re.compile(r"(\*\*(.+?)\*\*|`(.+?)`)")
    last_end = 0

    for match in pattern.finditer(text):
        # 매치 전 일반 텍스트
        if match.start() > last_end:
            plain = text[last_end:match.start()]
            if plain:
                nodes.append({"type": "text", "text": plain})

        if match.group(2):  # **bold**
            nodes.append({
                "type": "text",
                "text": match.group(2),
                "marks": [{"type": "strong"}],
            })
        elif match.group(3):  # `code`
            nodes.append({
                "type": "text",
                "text": match.group(3),
                "marks": [{"type": "code"}],
            })
        last_end = match.end()

    # 나머지 텍스트
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            nodes.append({"type": "text", "text": remaining})

    if not nodes:
        nodes.append({"type": "text", "text": text or " "})

    return nodes


async def search_issues(jql: str, max_results: int = 10) -> dict:
    """JQL을 사용해 Jira 이슈를 검색합니다."""
    client = _get_client()
    resp = await client.post(
        f"{settings.jira_base_url}/rest/api/3/search/jql",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "priority", "parent"],
        },
    )
    resp.raise_for_status()
    return resp.json()


async def get_issue(issue_key: str) -> dict:
    """특정 Jira 이슈의 상세 정보를 가져옵니다."""
    client = _get_client()
    resp = await client.get(
        f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}",
    )
    resp.raise_for_status()
    return resp.json()


async def create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    parent_key: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """새로운 Jira 이슈를 생성합니다."""
    issue_type_str = str(issue_type).strip()
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "description": _markdown_to_adf(description),
        "issuetype": {"id": issue_type_str} if issue_type_str.isdigit() else {"name": issue_type_str},
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if labels:
        fields["labels"] = labels
    payload = {"fields": fields}
    client = _get_client()
    resp = await client.post(
        f"{settings.jira_base_url}/rest/api/3/issue",
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


async def update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    status: str | None = None,
    assignee_account_id: str | None = None,
    priority: str | None = None,
    labels: list[str] | None = None,
) -> None:
    """Jira 이슈를 수정합니다."""
    fields: dict = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = _markdown_to_adf(description)
    if assignee_account_id is not None:
        fields["assignee"] = {"accountId": assignee_account_id}
    if priority is not None:
        fields["priority"] = {"name": priority}
    if labels is not None:
        fields["labels"] = labels

    client = _get_client()
    if fields:
        resp = await client.put(
            f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}",
            json={"fields": fields},
        )
        resp.raise_for_status()

    if status is not None:
        transitions_resp = await client.get(
            f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}/transitions",
        )
        transitions_resp.raise_for_status()
        transitions = transitions_resp.json()["transitions"]
        matched = [t for t in transitions if t["name"].lower() == status.lower()]
        if not matched:
            available = [t["name"] for t in transitions]
            raise ValueError(
                f"상태 '{status}'에 해당하는 전환을 찾을 수 없습니다. "
                f"가능한 상태: {available}"
            )
        await client.post(
            f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}/transitions",
            json={"transition": {"id": matched[0]["id"]}},
        )


async def attach_file(issue_key: str, file_path: str) -> list[dict]:
    """Jira 이슈에 파일을 첨부합니다."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    credentials = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "X-Atlassian-Token": "no-check",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(path, "rb") as f:
            resp = await client.post(
                f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}/attachments",
                headers=headers,
                files={"file": (path.name, f)},
            )
        resp.raise_for_status()
        return resp.json()


async def add_comment(issue_key: str, comment: str) -> dict:
    """Jira 이슈에 코멘트를 추가합니다."""
    payload = {
        "body": _markdown_to_adf(comment),
    }
    client = _get_client()
    resp = await client.post(
        f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}/comment",
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()
