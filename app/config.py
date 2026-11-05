"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str
    api_id: int = 0
    api_hash: str = ""
    owner_id: int

    # MongoDB
    mongo_uri: str = "mongodb://mongo:27017"
    mongo_db_name: str = "bot_hosting"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Encryption
    fernet_key: str

    # Anthropic Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # GitHub OAuth (Phase 6)
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_callback_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
