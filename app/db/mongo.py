"""MongoDB connection + Beanie initialization."""
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models import ALL_DOCUMENTS

log = get_logger("db")
_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _client
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongo_uri)
    await init_beanie(
        database=_client[settings.mongo_db_name],
        document_models=ALL_DOCUMENTS,
    )
    log.info("mongodb_connected", db=settings.mongo_db_name)


async def close_db() -> None:
    if _client is not None:
        _client.close()
        log.info("mongodb_closed")
