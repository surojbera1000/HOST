"""MongoDB document models (Beanie ODM)."""
from datetime import datetime, timezone
from enum import Enum

from beanie import Document
from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BotStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    CONFIGURING = "configuring"
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    FAILED = "failed"


class EnvVar(BaseModel):
    """A single environment variable — the value is encrypted when sensitive."""
    key: str
    value_encrypted: str
    is_sensitive: bool = True


class User(Document):
    telegram_id: int
    username: str | None = None
    full_name: str | None = None
    plan: str = "free"
    github_token_encrypted: str | None = None
    is_banned: bool = False
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "users"
        indexes = ["telegram_id"]


class HostedBot(Document):
    owner_id: int                       # telegram_id
    name: str = "Untitled Bot"
    repo_url: str | None = None
    branch: str = "main"
    language: str | None = None
    framework: str | None = None
    entrypoint: str | None = None
    startup_cmd: str | None = None
    env_vars: list[EnvVar] = Field(default_factory=list)
    container_id: str | None = None
    status: BotStatus = BotStatus.PENDING
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "bots"
        indexes = ["owner_id"]


class Deployment(Document):
    bot_id: str
    status: BotStatus = BotStatus.DEPLOYING
    logs: str = ""
    error_summary: str | None = None
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None

    class Settings:
        name = "deployments"
        indexes = ["bot_id"]


ALL_DOCUMENTS = [User, HostedBot, Deployment]
