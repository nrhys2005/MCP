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

    # Server
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()
