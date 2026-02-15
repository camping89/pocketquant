"""MongoDB connection manager — instance-based for DI container."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Database:
    """MongoDB connection manager. Instance-based, managed by DI container."""

    def __init__(self) -> None:
        self._client: AsyncMongoClient | None = None
        self._database: AsyncDatabase | None = None

    async def connect(self, settings: Settings) -> None:
        logger.info("mongodb.connecting", database=settings.mongodb_database)

        client = AsyncMongoClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
        )

        try:
            await client.server_info()
            self._client = client
            self._database = client[settings.mongodb_database]
            logger.info("mongodb.connected", database=settings.mongodb_database)
        except Exception as e:
            logger.error("mongodb.connection_failed", error=str(e))
            await client.close()
            raise

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._database = None
            logger.info("mongodb.disconnected")

    def get_database(self) -> AsyncDatabase:
        if self._database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return self._database

    def get_collection(self, name: str):
        return self.get_database()[name]


@asynccontextmanager
async def get_database(settings: Settings) -> AsyncGenerator[AsyncDatabase]:
    db = Database()
    try:
        await db.connect(settings)
        yield db.get_database()
    finally:
        await db.disconnect()
