"""MongoDB connection manager — instance-based for DI container."""

from __future__ import annotations

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings

logger = get_logger(__name__)


class Database:
    """MongoDB connection manager. Instance-based, managed by DI container.

    Public surface (in order of preference for app code):
    - get_collection(name) — preferred for repositories and CQRS handlers.
    - database (property) — raw AsyncDatabase for migrations, admin ops,
      and one-offs (rename_collection, list_collection_names, drop_index,
      bulk aggregations). Avoid in app/repository code.
    - get_database() — kept as alias of the `database` property for
      backward compatibility with existing call sites.

    Architecture notes:
    - __client: server-level connection (pool, auth, network). Kept private
      for disconnect() — accessing it via __database.client violates Law of
      Demeter.
    - __database: reference to one specific database on the server.
      Repositories receive this class and call get_collection() — they
      should not reach for `database` (Principle of Least Privilege).

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

    @property
    def database(self) -> AsyncDatabase:
        if self.__database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return self.__database

    def get_database(self) -> AsyncDatabase:
        return self.database

    def get_collection(self, name: str):
        return self.database[name]
