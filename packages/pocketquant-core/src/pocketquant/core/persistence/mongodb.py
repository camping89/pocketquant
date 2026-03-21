"""MongoDB connection manager — instance-based for DI container."""

from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient

logger = get_logger(__name__)


class Database:
    """MongoDB connection manager. Instance-based, managed by DI container.

    Architecture notes:
    - __client: server-level connection (manages connection pool, auth, network).
      Kept as private prop for disconnect() — without it we can't call .close()
      and connections would leak. Although __database.client exists, accessing
      parent from child is fragile and violates Law of Demeter.
    - __database: reference to one specific database on the server.
      Repositories receive this class and call get_collection() — they never
      see the client, following Principle of Least Privilege.

    Uses __ (name mangling) to enforce encapsulation — prevents external code
    from accessing internals. Only public methods (get_database, get_collection)
    should be used by consumers.

    Hierarchy: client (server) → database (one DB) → collection (one table)
    Only collections are used for CRUD; client/database handle lifecycle.
    """

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

    def get_database(self) -> AsyncDatabase:
        if self.__database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return self.__database

    def get_collection(self, name: str):
        return self.get_database()[name]
