"""Base repository mixin for MongoDB collections."""

from src.persistence.mongodb import Database


class BaseRepository:
    """Mixin providing collection access. Subclasses set _collection_name."""

    _collection_name: str

    @classmethod
    def _collection(cls):
        return Database.get_collection(cls._collection_name)
