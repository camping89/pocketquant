"""MongoDB async connection management using Motor."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Database:
    """MongoDB database connection manager."""

    _client: AsyncIOMotorClient | None = None
    _database: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        """Establish MongoDB connection.

        Args:
            settings: Application settings with MongoDB configuration.
        """
        logger.info(
            "connecting_to_mongodb",
            database=settings.mongodb_database,
        )

        cls._client = AsyncIOMotorClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
        )
        cls._database = cls._client[settings.mongodb_database]
        await cls._client.admin.command("ping")
        logger.info("mongodb_connected", database=settings.mongodb_database)

    @classmethod
    async def disconnect(cls) -> None:
        """Close MongoDB connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._database = None
            logger.info("mongodb_disconnected")

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """Get the database instance.

        Returns:
            The MongoDB database instance.

        Raises:
            RuntimeError: If database is not connected.
        """
        if cls._database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls._database

    @classmethod
    def get_collection(cls, name: str):
        """Get a collection from the database.

        Args:
            name: Collection name.

        Returns:
            The MongoDB collection.
        """
        return cls.get_database()[name]


@asynccontextmanager
async def get_database(settings: Settings) -> AsyncGenerator[AsyncIOMotorDatabase]:
    """Context manager for database connection.

    Args:
        settings: Application settings.

    Yields:
        The MongoDB database instance.
    """
    try:
        await Database.connect(settings)
        yield Database.get_database()
    finally:
        await Database.disconnect()
