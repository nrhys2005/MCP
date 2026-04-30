# MCP Server

Jira, Slack, Linear, Notion을 통합하는 MCP(Model Context Protocol) 서버입니다.

## 요구사항

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (패키지 매니저)

## 설치

```bash
# 의존성 설치
uv sync

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어 각 서비스의 API 키를 입력합니다
```

## 환경변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `JIRA_BASE_URL` | Jira 인스턴스 URL | `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | Jira 계정 이메일 | `user@example.com` |
| `JIRA_API_TOKEN` | Jira API 토큰 | [생성하기](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth 토큰 | `xoxb-...` |
| `SLACK_SIGNING_SECRET` | Slack Signing Secret | Slack App 설정에서 확인 |
| `LINEAR_API_KEY` | Linear API 키 | [생성하기](https://linear.app/settings/api) |
| `NOTION_API_KEY` | Notion Integration 토큰 | [생성하기](https://www.notion.so/my-integrations) |
| `MCP_HOST` | 서버 호스트 (기본값: `0.0.0.0`) | `0.0.0.0` |
| `MCP_PORT` | 서버 포트 (기본값: `8000`) | `8000` |

## 실행

```bash
# stdio 모드 (Claude Desktop 등에서 사용)
uv run mcp-server

# SSE 모드 (HTTP)
uv run python -c "from mcp_server.main import run_sse; run_sse()"

# FastAPI 서버 (health check 포함)
uv run python -m mcp_server.main
```

## Claude Desktop 설정

`claude_desktop_config.json`에 추가:

```json
{
  "mcpServers": {
    "mcp-server": {
      "command": "uv",
      "args": ["--directory", "/path/to/MCP", "run", "mcp-server"]
    }
  }
}
```

## 주요 기능

- **마크다운 변환**: Jira(마크다운→ADF), Notion(마크다운→블록) 자동 변환 지원
  - 헤딩, 리스트, 코드 블록, 테이블, 인용, 체크박스, 인라인 서식(bold, italic, strikethrough, code, link)
- **커서 페이지네이션**: Notion 대용량 데이터 조회 시 자동 페이지네이션
- **ID 정규화**: Notion 하이픈 없는 32자 ID를 UUID 형식으로 자동 변환
- **SSL 인증서**: truststore를 통한 시스템 인증서 저장소 자동 주입

## 제공 도구

### Jira (6개)

| 도구 | 설명 |
|------|------|
| `jira_search_issues` | JQL 쿼리로 이슈 검색 |
| `jira_get_issue` | 이슈 상세 조회 (하위 이슈 포함) |
| `jira_create_issue` | 이슈 생성 (상위 이슈, 라벨, 이슈 타입 ID 지원) |
| `jira_update_issue` | 이슈 수정 (상태 전환, 담당자, 우선순위, 라벨) |
| `jira_attach_file` | 이슈에 파일 첨부 |
| `jira_add_comment` | 이슈에 코멘트 추가 (마크다운→ADF 변환) |

### Slack (3개)

| 도구 | 설명 |
|------|------|
| `slack_send_message` | 채널에 메시지 전송 |
| `slack_list_channels` | 채널 목록 조회 |
| `slack_get_channel_history` | 채널 메시지 이력 조회 |

### Linear (7개)

| 도구 | 설명 |
|------|------|
| `linear_search_issues` | 이슈 검색 (프로젝트 필터 지원) |
| `linear_get_issue` | 이슈 상세 조회 (상하위 이슈, 코멘트 포함) |
| `linear_create_issue` | 이슈 생성 (우선순위, 상태, 프로젝트 지정) |
| `linear_update_issue` | 이슈 수정 |
| `linear_add_comment` | 이슈에 코멘트 추가 |
| `linear_list_teams` | 팀 목록 및 워크플로 상태 조회 |
| `linear_list_projects` | 프로젝트 목록 조회 |

### Notion (8개)

| 도구 | 설명 |
|------|------|
| `notion_search` | 페이지/데이터베이스 검색 |
| `notion_get_page` | 페이지 속성 조회 |
| `notion_create_page` | 페이지 생성 (마크다운 본문 지원) |
| `notion_update_page` | 페이지 속성 수정 |
| `notion_get_database` | 데이터베이스 스키마 조회 |
| `notion_query_database` | 데이터베이스 쿼리 (필터/정렬, 커서 페이지네이션) |
| `notion_get_page_content` | 페이지 본문 블록 조회 (커서 페이지네이션) |
| `notion_append_content` | 페이지에 마크다운 콘텐츠 추가 |

## 프로젝트 구조

```
src/mcp_server/
├── main.py          # MCP 서버 엔트리포인트 및 도구 등록
├── config.py        # 환경변수 설정 (pydantic-settings)
└── tools/
    ├── jira.py      # Jira REST API 클라이언트 (마크다운→ADF 변환)
    ├── slack.py     # Slack Web API 클라이언트
    ├── linear.py    # Linear GraphQL API 클라이언트
    └── notion.py    # Notion REST API 클라이언트 (마크다운→블록 변환, 페이지네이션)
```
