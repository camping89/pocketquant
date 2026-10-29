from __future__ import annotations

from datetime import UTC

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings

logger = get_logger(__name__)


class Database:
    def __init__(self) -> None:
        self.__client: AsyncMongoClient | None = None
        self.__database: AsyncDatabase | None = None

    async def connect(self, settings: Settings) -> None:
        logger.info("mongodb.connecting", database=settings.mongodb_database)

        client = AsyncMongoClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
            # BSON stores UTC instants but decodes them naive by default, which
            # makes every read a place where a zone can be re-guessed.
            tz_aware=True,
            tzinfo=UTC,
        )

        try:
            await client.server_info()
            self.__client = client
            self.__database = client[settings.mongodb_database]
            logger.info("mongodb.connected", database=settings.mongodb_database)
        except Exception as e:
            logger.error("mongodb.connection_failed", error=str(e))
            await client.close()
            raise

    async def disconnect(self) -> None:
        if self.__client is not None:
            await self.__client.close()
            self.__client = None
            self.__database = None
            logger.info("mongodb.disconnected")

    # Raw database for migrations and admin ops; repositories use get_collection().
    @property
    def database(self) -> AsyncDatabase:
        if self.__database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return self.__database

    def get_database(self) -> AsyncDatabase:
        return self.database

    def get_collection(self, name: str):
        return self.database[name]
