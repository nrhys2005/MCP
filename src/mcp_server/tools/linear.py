import httpx

from mcp_server.config import settings

LINEAR_API = "https://api.linear.app/graphql"


def _headers() -> dict[str, str]:
    return {
        "Authorization": settings.linear_api_key,
        "Content-Type": "application/json",
    }


async def _graphql(query: str, variables: dict | None = None) -> dict:
    """Linear GraphQL API를 호출합니다."""
    body: dict = {"query": query}
    if variables:
        body["variables"] = variables
    async with httpx.AsyncClient() as client:
        resp = await client.post(LINEAR_API, headers=_headers(), json=body, timeout=30.0)
        resp.raise_for_status()
        result = resp.json()
        if "errors" in result:
            raise RuntimeError(f"Linear API error: {result['errors']}")
        return result["data"]


async def search_issues(query: str, limit: int = 10, project_name: str | None = None) -> dict:
    """이슈를 검색합니다."""
    gql = """
    query($filter: IssueFilter, $first: Int) {
      issues(filter: $filter, first: $first) {
        nodes {
          id identifier title
          state { name }
          assignee { name }
          priority priorityLabel
          team { key name }
          project { name }
        }
      }
    }
    """
    filter_obj: dict = {
        "or": [
            {"title": {"containsIgnoreCase": query}},
            {"description": {"containsIgnoreCase": query}},
        ]
    }
    if project_name:
        filter_obj = {
            "and": [
                filter_obj,
                {"project": {"name": {"eqIgnoreCase": project_name}}},
            ]
        }
    data = await _graphql(gql, {"filter": filter_obj, "first": limit})
    return data["issues"]


async def get_issue(issue_id: str) -> dict:
    """이슈 상세 정보를 조회합니다 (ID 또는 identifier)."""
    gql = """
    query($id: String!) {
      issue(id: $id) {
        id identifier title description
        state { name }
        assignee { name email }
        priority priorityLabel
        team { key name }
        labels { nodes { name } }
        createdAt updatedAt
        parent { identifier title }
        children { nodes { identifier title state { name } } }
        comments { nodes { body user { name } createdAt } }
      }
    }
    """
    data = await _graphql(gql, {"id": issue_id})
    return data["issue"]


async def create_issue(
    team_id: str,
    title: str,
    description: str = "",
    priority: int | None = None,
    assignee_id: str | None = None,
    state_id: str | None = None,
    label_ids: list[str] | None = None,
    project_id: str | None = None,
) -> dict:
    """새 이슈를 생성합니다."""
    gql = """
    mutation($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title url project { name } }
      }
    }
    """
    input_obj: dict = {"teamId": team_id, "title": title}
    if description:
        input_obj["description"] = description
    if priority is not None:
        input_obj["priority"] = priority
    if assignee_id:
        input_obj["assigneeId"] = assignee_id
    if state_id:
        input_obj["stateId"] = state_id
    if label_ids:
        input_obj["labelIds"] = label_ids
    if project_id:
        input_obj["projectId"] = project_id
    data = await _graphql(gql, {"input": input_obj})
    return data["issueCreate"]


async def update_issue(
    issue_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    assignee_id: str | None = None,
    state_id: str | None = None,
    label_ids: list[str] | None = None,
) -> dict:
    """이슈를 수정합니다."""
    gql = """
    mutation($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
        issue { id identifier title state { name } assignee { name } priorityLabel }
      }
    }
    """
    input_obj: dict = {}
    if title is not None:
        input_obj["title"] = title
    if description is not None:
        input_obj["description"] = description
    if priority is not None:
        input_obj["priority"] = priority
    if assignee_id is not None:
        input_obj["assigneeId"] = assignee_id
    if state_id is not None:
        input_obj["stateId"] = state_id
    if label_ids is not None:
        input_obj["labelIds"] = label_ids
    data = await _graphql(gql, {"id": issue_id, "input": input_obj})
    return data["issueUpdate"]


async def add_comment(issue_id: str, body: str) -> dict:
    """이슈에 코멘트를 추가합니다."""
    gql = """
    mutation($input: CommentCreateInput!) {
      commentCreate(input: $input) {
        success
        comment { id body createdAt user { name } }
      }
    }
    """
    data = await _graphql(gql, {"input": {"issueId": issue_id, "body": body}})
    return data["commentCreate"]


async def list_teams() -> list[dict]:
    """팀 목록을 조회합니다."""
    gql = """
    query {
      teams {
        nodes { id key name states { nodes { id name } } }
      }
    }
    """
    data = await _graphql(gql)
    return data["teams"]["nodes"]


async def list_projects(first: int = 20) -> list[dict]:
    """프로젝트 목록을 조회합니다."""
    gql = """
    query($first: Int) {
      projects(first: $first) {
        nodes { id name state teams { nodes { key } } }
      }
    }
    """
    data = await _graphql(gql, {"first": first})
    return data["projects"]["nodes"]
