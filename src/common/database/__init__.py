"""MongoDB database module - re-exports from infrastructure."""

from src.persistence import Database, get_database

__all__ = ["Database", "get_database"]
