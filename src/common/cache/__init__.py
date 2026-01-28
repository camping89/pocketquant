"""Redis cache module - re-exports from infrastructure."""

from src.infrastructure.persistence import Cache, get_cache

__all__ = ["Cache", "get_cache"]
