"""Base repository mixin for MongoDB collections."""

from __future__ import annotations

from src.persistence.mongodb import Database


class BaseRepository:
    """Base repository with DI-injected Database instance.

    Subclasses set _collection_name and receive Database via constructor.
    """

    _collection_name: str

    def __init__(self, database: Database) -> None:
        self._database = database

    def _collection(self):
        return self._database.get_collection(self._collection_name)
