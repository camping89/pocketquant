"""MongoDB database module - re-exports from infrastructure."""

from src.infrastructure.persistence import Database, get_database

__all__ = ["Database", "get_database"]
