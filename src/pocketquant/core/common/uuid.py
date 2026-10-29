from uuid import UUID, uuid7

__all__ = ["UUID", "generate_id", "generate_id_str"]


def generate_id() -> UUID:
    return uuid7()


def generate_id_str() -> str:
    return str(uuid7())
