"""UUID generation utilities.

Uses Python 3.14's native uuid7() for time-ordered UUIDs.
Benefits: chronological sorting, better DB index performance.
"""

from uuid import UUID, uuid7

__all__ = ["UUID", "generate_id", "generate_id_str"]


def generate_id() -> UUID:
    """Generate a time-ordered UUID v7."""
    return uuid7()


def generate_id_str() -> str:
    """Generate a time-ordered UUID v7 as string."""
    return str(uuid7())
