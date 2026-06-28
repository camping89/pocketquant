"""Sync status repository for MongoDB persistence."""

from datetime import UTC, datetime

from pymongo import ReturnDocument

from pocketquant.core.common.constants import COLLECTION_SYNC_STATUS
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status import SyncStatus
from pocketquant.core.infra.persistence.base_repository import BaseRepository


class SyncStatusRepository(BaseRepository):
    """Repository for sync status tracking. ``symbol`` is composite ``{code}:{exchange}``."""

    _collection_name = COLLECTION_SYNC_STATUS

    async def upsert(
        self,
        symbol: str,
        interval: Interval,
        status: str,
        bar_count: int | None = None,
        last_bar_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        collection = self._collection()

        update_doc = {
            "symbol": symbol.upper(),
            "interval": interval.value,
            "status": status,
            "last_sync_at": datetime.now(UTC),
            "bar_count": bar_count or 0,
            "last_bar_at": last_bar_at,
            "error_message": error_message,
        }

        await collection.update_one(
            {
                "symbol": symbol.upper(),
                "interval": interval.value,
            },
            {
                "$set": update_doc,
                "$setOnInsert": {"_id": generate_id_str()},
            },
            upsert=True,
        )

    async def find_all(self) -> list[SyncStatus]:
        collection = self._collection()
        cursor = collection.find()
        return [SyncStatus.from_mongo(doc) async for doc in cursor]

    async def bump_empty_fetch(self, symbol: str, interval: Interval) -> int:
        """Atomic $inc on consecutive_empty_fetches.

        Despite the legacy name, this counter tracks any non-progress sync
        (``inserted == 0`` with existing data), including all-misaligned and
        fully-filtered-existing cases. Reset by ``reset_empty_fetch`` on
        successful insert. Returns the new count.
        """
        res = await self._collection().find_one_and_update(
            {
                "symbol": symbol.upper(),
                "interval": interval.value,
            },
            {"$inc": {"consecutive_empty_fetches": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return int(res.get("consecutive_empty_fetches", 0)) if res else 0

    async def reset_empty_fetch(self, symbol: str, interval: Interval) -> None:
        await self._collection().update_one(
            {
                "symbol": symbol.upper(),
                "interval": interval.value,
            },
            {"$set": {"consecutive_empty_fetches": 0}},
        )

    async def find_one(self, symbol: str, interval: Interval) -> SyncStatus | None:
        collection = self._collection()

        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "interval": interval.value,
            }
        )

        return SyncStatus.from_mongo(doc) if doc else None

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("interval", 1)],
            unique=True,
            name="ix_sync_status_symbol_interval",
        )
