from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Database:
    _client: AsyncMongoClient | None = None
    _database: AsyncDatabase | None = None

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        logger.info(
            "connecting_to_mongodb",
            database=settings.mongodb_database,
        )

        client = AsyncMongoClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
        )

        try:
            await client.server_info()
            cls._client = client
            cls._database = client[settings.mongodb_database]
            logger.info("mongodb_connected", database=settings.mongodb_database)
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            await client.close()
            raise

    @classmethod
    async def disconnect(cls) -> None:
        if cls._client is not None:
            await cls._client.close()
            cls._client = None
            cls._database = None
            logger.info("mongodb_disconnected")

    @classmethod
    def get_database(cls) -> AsyncDatabase:
        if cls._database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls._database

    @classmethod
    def get_collection(cls, name: str):
        return cls.get_database()[name]


@asynccontextmanager
async def get_database(settings: Settings) -> AsyncGenerator[AsyncDatabase]:
    try:
        await Database.connect(settings)
        yield Database.get_database()
    finally:
        await Database.disconnect()
