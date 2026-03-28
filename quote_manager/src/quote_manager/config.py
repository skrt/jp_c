"""Application configuration via environment variables."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # Paths
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    data_dir: Path = base_dir / "data"

    # Gmail
    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "data/token.json"

    # Slack
    slack_bot_token: str = ""
    slack_channel_ids: str = ""  # comma-separated

    # Anthropic API
    anthropic_api_key: str = ""

    # Database
    database_url: str = "sqlite:///data/quotes.db"

    # Export
    default_currency: str = "JPY"
    company_name: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def slack_channels(self) -> list[str]:
        """Parse comma-separated Slack channel IDs."""
        if not self.slack_channel_ids:
            return []
        return [c.strip() for c in self.slack_channel_ids.split(",") if c.strip()]

    @property
    def attachments_dir(self) -> Path:
        path = self.data_dir / "attachments"
        path.mkdir(parents=True, exist_ok=True)
        return path


def get_settings() -> Settings:
    return Settings()
