import base64
import re
from pathlib import Path

import httpx

from mcp_server.config import settings

_DEFAULT_TIMEOUT = 30.0
_ALLOWED_ATTACH_DIRS = ("/tmp", "/var/tmp")

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        credentials = base64.b64encode(
            f"{settings.jira_email}:{settings.jira_api_token}".encode()
        ).decode()
        _client = httpx.AsyncClient(
            base_url=settings.jira_base_url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            timeout=_DEFAULT_TIMEOUT,
        )
    return _client


def _raise_for_status(resp: httpx.Response) -> None:
    """4xx/5xx 응답 시 body 를 포함한 명확한 에러 raise.

    기본 ``httpx.raise_for_status()`` 는 status code 만 노출해 Atlassian API 의
    ``errors`` / ``errorMessages`` 필드를 가려버린다. 본 헬퍼는 그 body 를
    그대로 메시지에 포함해 어느 필드가 누락됐는지 즉시 가시화한다.
    """
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:  # noqa: BLE001
        detail = resp.text
    raise httpx.HTTPStatusError(
        f"Jira API {resp.status_code} {resp.reason_phrase}: {detail}",
        request=resp.request,
        response=resp,
    )


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

        # 코드 블록 (```)
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

        # Jira 위키 코드 블록 ({code}, {code:sql}, {noformat})
        # ``{code:lang}`` 처럼 콜론 + 언어 지정 변형도 인식한다.
        wiki_code_match = re.match(r"^\{(code|noformat)(?::([^}]+))?\}$", line.strip())
        if wiki_code_match:
            language = wiki_code_match.group(2)
            code_lines = []
            i += 1
            while i < len(lines) and not re.match(
                r"^\{(code|noformat)(?::[^}]+)?\}$", lines[i].strip()
            ):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # {code} 닫기 스킵
            attrs = {}
            if language:
                attrs["language"] = language
            content.append({
                "type": "codeBlock",
                "attrs": attrs,
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
    resp = await _get_client().post(
        "/rest/api/3/search/jql",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "priority", "parent"],
        },
    )
    _raise_for_status(resp)
    return resp.json()


async def get_issue(issue_key: str) -> dict:
    """특정 Jira 이슈의 상세 정보를 가져옵니다."""
    resp = await _get_client().get(f"/rest/api/3/issue/{issue_key}")
    _raise_for_status(resp)
    return resp.json()


async def get_create_meta(project_key: str, issue_type_name: str | None = None) -> dict:
    """프로젝트의 issue type 별 필수/선택 필드 메타데이터를 조회합니다.

    필수 커스텀 필드(예: Sprint, Story Points) 식별 + ID 매핑 확인용.
    """
    params: dict = {
        "projectKeys": project_key,
        "expand": "projects.issuetypes.fields",
    }
    if issue_type_name:
        params["issuetypeNames"] = issue_type_name
    resp = await _get_client().get("/rest/api/3/issue/createmeta", params=params)
    _raise_for_status(resp)
    return resp.json()


async def create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    parent_key: str | None = None,
    labels: list[str] | None = None,
    custom_fields: dict | None = None,
) -> dict:
    """새로운 Jira 이슈를 생성합니다.

    ``custom_fields`` 로 ``customfield_10020`` (Sprint), ``customfield_10026``
    (Story Points) 등 프로젝트 required 필드를 자유롭게 전달할 수 있다.
    """
    issue_type_str = str(issue_type).strip()
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"id": issue_type_str} if issue_type_str.isdigit() else {"name": issue_type_str},
    }
    # description 이 빈 문자열이면 ADF 빈 doc 으로 전달하지 않고 필드 자체를 생략.
    # Atlassian API 는 빈 content 의 ADF 를 거부할 수 있음.
    if description:
        fields["description"] = _markdown_to_adf(description)
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if labels:
        fields["labels"] = labels
    if custom_fields:
        fields.update(custom_fields)
    resp = await _get_client().post("/rest/api/3/issue", json={"fields": fields})
    _raise_for_status(resp)
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
            f"/rest/api/3/issue/{issue_key}",
            json={"fields": fields},
        )
        _raise_for_status(resp)

    if status is not None:
        transitions_resp = await client.get(
            f"/rest/api/3/issue/{issue_key}/transitions",
        )
        _raise_for_status(transitions_resp)
        transitions = transitions_resp.json()["transitions"]
        matched = False
        status_lower = status.lower()
        for t in transitions:
            # transition name (전환 동작명) 또는 to.name (목표 상태명) 둘 다 매칭.
            # 한국어 워크플로에서 transition name 이 "완료처리" 이고 to.name 이
            # "Done" 인 경우, 사용자가 "Done" 으로 호출해도 매칭되도록 한다.
            t_name = t["name"].lower()
            t_to_name = t.get("to", {}).get("name", "").lower()
            if status_lower in (t_name, t_to_name):
                resp = await client.post(
                    f"/rest/api/3/issue/{issue_key}/transitions",
                    json={"transition": {"id": t["id"]}},
                )
                _raise_for_status(resp)
                matched = True
                break
        if not matched:
            available = [
                f'{t["name"]} → {t.get("to", {}).get("name", "?")}' for t in transitions
            ]
            raise ValueError(
                f"상태 전환 '{status}'을(를) 찾을 수 없습니다. "
                f"가능한 (transition → to): {available}"
            )


async def attach_file(issue_key: str, file_path: str) -> list[dict]:
    """Jira 이슈에 파일을 첨부합니다."""
    path = Path(file_path).resolve()

    # 경로 순회 방지: 허용된 디렉토리만 접근 가능
    if not any(str(path).startswith(d) for d in _ALLOWED_ATTACH_DIRS):
        raise PermissionError(
            f"허용되지 않은 경로입니다: {path}. 허용 디렉토리: {_ALLOWED_ATTACH_DIRS}"
        )
    if not path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    credentials = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=60.0) as upload_client:
        with open(path, "rb") as f:
            resp = await upload_client.post(
                f"{settings.jira_base_url}/rest/api/3/issue/{issue_key}/attachments",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "X-Atlassian-Token": "no-check",
                },
                files={"file": (path.name, f)},
            )
    _raise_for_status(resp)
    return resp.json()


async def add_comment(issue_key: str, comment: str) -> dict:
    """Jira 이슈에 코멘트를 추가합니다."""
    resp = await _get_client().post(
        f"/rest/api/3/issue/{issue_key}/comment",
        json={"body": _markdown_to_adf(comment)},
    )
    _raise_for_status(resp)
    return resp.json()


async def get_comments(issue_key: str) -> dict:
    """Jira 이슈의 코멘트 목록을 조회합니다."""
    resp = await _get_client().get(f"/rest/api/3/issue/{issue_key}/comment")
    _raise_for_status(resp)
    return resp.json()


async def delete_comment(issue_key: str, comment_id: str) -> None:
    """Jira 이슈의 코멘트를 삭제합니다.

    삭제 권한이 없으면 403, 코멘트가 존재하지 않으면 404 를 반환한다.
    성공 시 204 No Content.
    """
    resp = await _get_client().delete(
        f"/rest/api/3/issue/{issue_key}/comment/{comment_id}"
    )
    _raise_for_status(resp)


async def delete_issue(issue_key: str, delete_subtasks: bool = False) -> None:
    """Jira 이슈를 삭제합니다.

    삭제 권한이 없으면 403, 이슈가 존재하지 않으면 404 를 반환한다.
    하위 작업이 있는데 delete_subtasks=False 면 400 을 반환한다.
    성공 시 204 No Content.

    빈 ``issue_key`` 가 들어오면 ``/rest/api/3/issue/`` 로 잘못된 DELETE 가 나가
    Atlassian 측에서 405 / collection endpoint 동작이 섞일 수 있어 호출 측
    버그가 가려진다. 클라이언트 단에서 fail-fast.
    """
    cleaned_key = issue_key.strip()
    if not cleaned_key:
        raise ValueError("issue_key cannot be empty")
    resp = await _get_client().delete(
        f"/rest/api/3/issue/{cleaned_key}",
        params={"deleteSubtasks": "true" if delete_subtasks else "false"},
    )
    _raise_for_status(resp)
