from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Jira
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # Linear
    linear_api_key: str = ""

    # Notion
    notion_api_key: str = ""

    # Server
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        # .env에는 이 서버가 쓰지 않는 변수(SLACK_APP_TOKEN 등)도 들어있다.
        # 기본값(extra_forbidden)이면 그런 변수 하나에 서버 전체가 기동 실패하므로 무시한다.
        "extra": "ignore",
    }


settings = Settings()
