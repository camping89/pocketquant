"""Lease repository: one document per role name says which process may act.

Acquire and renew are one conditional upsert; the unique name index makes a second
insert fail, so two contenders never both win. Wall-clock time: all roles share one
host clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.constants import COLLECTION_LEASES
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class LeaseRepository(BaseRepository):
    _collection_name = COLLECTION_LEASES

    async def acquire(self, name: str, owner: str, ttl_s: float) -> datetime | None:
        """Take or renew ``name`` for ``owner``; the new expiry, or None while another holds it."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_s)
        try:
            await self._collection().update_one(
                {"name": name, "$or": [{"expires_at": {"$lt": now}}, {"owner": owner}]},
                {
                    "$set": {"owner": owner, "expires_at": expires_at, "renewed_at": now},
                    "$setOnInsert": {"_id": generate_id_str()},
                },
                upsert=True,
            )
        except DuplicateKeyError:
            return None
        return expires_at

    async def release(self, name: str, owner: str) -> None:
        now = datetime.now(UTC)
        result = await self._collection().update_one(
            {"name": name, "owner": owner}, {"$set": {"expires_at": now, "released_at": now}}
        )
        if result.modified_count:
            logger.info("lease.released", name=name, owner=owner)

    async def get(self, name: str) -> dict[str, Any] | None:
        return await self._collection().find_one({"name": name})

    async def ensure_indexes(self) -> None:
        await self._collection().create_index("name", unique=True, name="ux_leases_name")
