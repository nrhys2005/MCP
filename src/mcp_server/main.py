import json
import logging

import uvicorn
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from mcp_server.config import settings
from mcp_server.tools import jira, linear, slack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MCP 서버 생성
mcp = FastMCP("MCP Server")


# ── Jira Tools ──────────────────────────────────────────────


@mcp.tool()
async def jira_search_issues(jql: str, max_results: int = 10) -> str:
    """JQL 쿼리로 Jira 이슈를 검색합니다.

    Args:
        jql: JQL 쿼리 문자열 (예: "project = PROJ AND status = 'In Progress'")
        max_results: 최대 결과 수
    """
    result = await jira.search_issues(jql, max_results)
    issues = []
    for issue in result.get("issues", []):
        issue_data = {
            "key": issue.get("key", issue.get("id", "unknown")),
            "summary": issue.get("fields", {}).get("summary", ""),
            "status": issue.get("fields", {}).get("status", {}).get("name", ""),
            "assignee": (issue.get("fields", {}).get("assignee") or {}).get("displayName", "Unassigned"),
        }
        issues.append(issue_data)
    if not issues and result.get("total", 0) > 0:
        return json.dumps({"raw_keys": list(result.keys()), "total": result.get("total")}, ensure_ascii=False, indent=2)
    return json.dumps(issues, ensure_ascii=False, indent=2)


@mcp.tool()
async def jira_get_issue(issue_key: str) -> str:
    """특정 Jira 이슈의 상세 정보를 조회합니다.

    Args:
        issue_key: 이슈 키 (예: "PROJ-123")
    """
    issue = await jira.get_issue(issue_key)
    fields = issue["fields"]
    result = {
        "key": issue["key"],
        "summary": fields["summary"],
        "status": fields["status"]["name"],
        "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
        "priority": (fields.get("priority") or {}).get("name", "None"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "description": fields.get("description"),
    }
    subtasks = fields.get("subtasks", [])
    if subtasks:
        result["subtasks"] = [
            {
                "key": s["key"],
                "summary": s["fields"]["summary"],
                "status": s["fields"]["status"]["name"],
            }
            for s in subtasks
        ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def jira_create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
) -> str:
    """새로운 Jira 이슈를 생성합니다.

    Args:
        project_key: 프로젝트 키 (예: "PROJ")
        summary: 이슈 제목
        description: 이슈 설명
        issue_type: 이슈 타입 (Task, Bug, Story 등)
    """
    result = await jira.create_issue(project_key, summary, description, issue_type)
    return json.dumps(
        {"key": result["key"], "self": result["self"]},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def jira_update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    status: str | None = None,
    assignee_account_id: str | None = None,
    priority: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """Jira 이슈를 수정합니다. 변경할 필드만 전달하면 됩니다.

    Args:
        issue_key: 이슈 키 (예: "PROJ-123")
        summary: 변경할 이슈 제목
        description: 변경할 이슈 설명
        status: 변경할 상태 (예: "In Progress", "Done")
        assignee_account_id: 담당자 Account ID
        priority: 우선순위 (예: "High", "Medium", "Low")
        labels: 라벨 목록
    """
    await jira.update_issue(
        issue_key,
        summary=summary,
        description=description,
        status=status,
        assignee_account_id=assignee_account_id,
        priority=priority,
        labels=labels,
    )
    updated = await jira.get_issue(issue_key)
    fields = updated["fields"]
    result = {
        "key": updated["key"],
        "summary": fields["summary"],
        "status": fields["status"]["name"],
        "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
        "priority": (fields.get("priority") or {}).get("name", "None"),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def jira_attach_file(issue_key: str, file_path: str) -> str:
    """Jira 이슈에 파일을 첨부합니다.

    Args:
        issue_key: 이슈 키 (예: "PROJ-123")
        file_path: 첨부할 파일의 절대 경로
    """
    result = await jira.attach_file(issue_key, file_path)
    attachments = [
        {"filename": a["filename"], "size": a["size"], "id": a["id"]}
        for a in result
    ]
    return json.dumps(attachments, ensure_ascii=False, indent=2)


@mcp.tool()
async def jira_add_comment(issue_key: str, comment: str) -> str:
    """Jira 이슈에 코멘트를 추가합니다.

    Args:
        issue_key: 이슈 키 (예: "PROJ-123")
        comment: 코멘트 내용
    """
    result = await jira.add_comment(issue_key, comment)
    return json.dumps({"id": result["id"], "created": result["created"]}, indent=2)


# ── Slack Tools ─────────────────────────────────────────────


@mcp.tool()
async def slack_send_message(channel: str, text: str) -> str:
    """Slack 채널에 메시지를 전송합니다.

    Args:
        channel: 채널명 또는 채널 ID (예: "#general" 또는 "C01234567")
        text: 전송할 메시지 내용
    """
    result = await slack.send_message(channel, text)
    if result.get("ok"):
        return json.dumps(
            {"ok": True, "channel": result["channel"], "ts": result["ts"]},
            indent=2,
        )
    return json.dumps({"ok": False, "error": result.get("error")}, indent=2)


@mcp.tool()
async def slack_list_channels(limit: int = 100) -> str:
    """Slack 채널 목록을 조회합니다.

    Args:
        limit: 최대 채널 수
    """
    result = await slack.list_channels(limit)
    channels = [
        {"id": ch["id"], "name": ch["name"], "topic": ch.get("topic", {}).get("value", "")}
        for ch in result.get("channels", [])
    ]
    return json.dumps(channels, ensure_ascii=False, indent=2)


@mcp.tool()
async def slack_get_channel_history(channel: str, limit: int = 20) -> str:
    """Slack 채널의 최근 메시지를 조회합니다.

    Args:
        channel: 채널 ID (예: "C01234567")
        limit: 최대 메시지 수
    """
    result = await slack.get_channel_history(channel, limit)
    messages = [
        {"user": msg.get("user", "bot"), "text": msg.get("text", ""), "ts": msg["ts"]}
        for msg in result.get("messages", [])
    ]
    return json.dumps(messages, ensure_ascii=False, indent=2)


# ── Linear Tools ────────────────────────────────────────────


@mcp.tool()
async def linear_search_issues(query: str, project_name: str | None = None, limit: int = 10) -> str:
    """Linear에서 이슈를 검색합니다.

    Args:
        query: 검색어 (제목/설명에서 검색)
        project_name: 프로젝트명으로 필터 (예: "momentsome")
        limit: 최대 결과 수
    """
    result = await linear.search_issues(query, limit, project_name)
    issues = [
        {
            "identifier": node["identifier"],
            "title": node["title"],
            "status": node["state"]["name"],
            "assignee": (node.get("assignee") or {}).get("name", "Unassigned"),
            "priority": node.get("priorityLabel", ""),
            "team": node.get("team", {}).get("key", ""),
            "project": (node.get("project") or {}).get("name", ""),
        }
        for node in result.get("nodes", [])
    ]
    return json.dumps(issues, ensure_ascii=False, indent=2)


@mcp.tool()
async def linear_get_issue(issue_id: str) -> str:
    """Linear 이슈의 상세 정보를 조회합니다.

    Args:
        issue_id: 이슈 ID 또는 identifier (예: "ENG-123")
    """
    issue = await linear.get_issue(issue_id)
    result = {
        "identifier": issue["identifier"],
        "title": issue["title"],
        "description": issue.get("description", ""),
        "status": issue["state"]["name"],
        "assignee": (issue.get("assignee") or {}).get("name", "Unassigned"),
        "priority": issue.get("priorityLabel", ""),
        "team": issue.get("team", {}).get("name", ""),
        "labels": [l["name"] for l in issue.get("labels", {}).get("nodes", [])],
        "createdAt": issue.get("createdAt"),
        "updatedAt": issue.get("updatedAt"),
    }
    parent = issue.get("parent")
    if parent:
        result["parent"] = {"identifier": parent["identifier"], "title": parent["title"]}
    children = issue.get("children", {}).get("nodes", [])
    if children:
        result["children"] = [
            {"identifier": c["identifier"], "title": c["title"], "status": c["state"]["name"]}
            for c in children
        ]
    comments = issue.get("comments", {}).get("nodes", [])
    if comments:
        result["comments"] = [
            {"body": c["body"], "user": c["user"]["name"], "createdAt": c["createdAt"]}
            for c in comments
        ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def linear_create_issue(
    team_id: str,
    title: str,
    description: str = "",
    priority: int | None = None,
    assignee_id: str | None = None,
    state_id: str | None = None,
    project_id: str | None = None,
) -> str:
    """Linear에 새 이슈를 생성합니다.

    Args:
        team_id: 팀 ID (linear_list_teams로 확인 가능)
        title: 이슈 제목
        description: 이슈 설명 (마크다운 지원)
        priority: 우선순위 (0=없음, 1=긴급, 2=높음, 3=보통, 4=낮음)
        assignee_id: 담당자 ID
        state_id: 상태 ID (linear_list_teams에서 확인 가능)
        project_id: 프로젝트 ID (linear_list_projects로 확인 가능)
    """
    result = await linear.create_issue(
        team_id, title, description, priority, assignee_id, state_id, project_id=project_id,
    )
    issue = result.get("issue", {})
    return json.dumps(
        {
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "url": issue.get("url"),
            "project": (issue.get("project") or {}).get("name", ""),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def linear_update_issue(
    issue_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    assignee_id: str | None = None,
    state_id: str | None = None,
) -> str:
    """Linear 이슈를 수정합니다. 변경할 필드만 전달하면 됩니다.

    Args:
        issue_id: 이슈 ID 또는 identifier (예: "ENG-123")
        title: 변경할 제목
        description: 변경할 설명
        priority: 변경할 우선순위 (0=없음, 1=긴급, 2=높음, 3=보통, 4=낮음)
        assignee_id: 변경할 담당자 ID
        state_id: 변경할 상태 ID
    """
    result = await linear.update_issue(
        issue_id, title, description, priority, assignee_id, state_id,
    )
    issue = result.get("issue", {})
    return json.dumps(
        {
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "status": issue.get("state", {}).get("name", ""),
            "assignee": (issue.get("assignee") or {}).get("name", "Unassigned"),
            "priority": issue.get("priorityLabel", ""),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def linear_add_comment(issue_id: str, body: str) -> str:
    """Linear 이슈에 코멘트를 추가합니다.

    Args:
        issue_id: 이슈 ID 또는 identifier (예: "ENG-123")
        body: 코멘트 내용 (마크다운 지원)
    """
    result = await linear.add_comment(issue_id, body)
    comment = result.get("comment", {})
    return json.dumps(
        {"id": comment.get("id"), "createdAt": comment.get("createdAt")},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def linear_list_teams() -> str:
    """Linear 팀 목록과 각 팀의 상태(workflow) 목록을 조회합니다."""
    teams = await linear.list_teams()
    result = [
        {
            "id": t["id"],
            "key": t["key"],
            "name": t["name"],
            "states": [{"id": s["id"], "name": s["name"]} for s in t.get("states", {}).get("nodes", [])],
        }
        for t in teams
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def linear_list_projects(limit: int = 20) -> str:
    """Linear 프로젝트 목록을 조회합니다.

    Args:
        limit: 최대 결과 수
    """
    projects = await linear.list_projects(limit)
    result = [
        {
            "id": p["id"],
            "name": p["name"],
            "state": p.get("state", ""),
            "teams": [t["key"] for t in p.get("teams", {}).get("nodes", [])],
        }
        for p in projects
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── FastAPI integration ─────────────────────────────────────

app = FastAPI(title="MCP Server")


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    """stdio 모드로 MCP 서버를 실행합니다."""
    mcp.run(transport="stdio")


def run_sse():
    """SSE 모드로 MCP 서버를 실행합니다 (HTTP)."""
    mcp.run(transport="sse")


if __name__ == "__main__":
    uvicorn.run(
        "mcp_server.main:app",
        host=settings.mcp_host,
        port=settings.mcp_port,
        reload=True,
    )
