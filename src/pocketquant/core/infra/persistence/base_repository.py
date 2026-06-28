"""Base repository mixin for MongoDB collections."""

from __future__ import annotations

from pocketquant.core.infra.persistence.mongodb import Database


class BaseRepository:
    _collection_name: str

    def __init__(self, database: Database) -> None:
        self._database = database

    def _collection(self):
        return self._database.get_collection(self._collection_name)
