"""Safeguards repository: one document holds the entry pause of the Exness safeguards.

No index; the collection holds one document.
"""

from datetime import UTC, datetime

from pocketquant.core.common.constants import COLLECTION_SAFEGUARDS
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.infra.persistence.base_repository import BaseRepository


class SafeguardsRepository(BaseRepository):
    _collection_name = COLLECTION_SAFEGUARDS

    async def load_entries_paused(self) -> bool:
        doc = await self._collection().find_one({})
        return bool(doc and doc.get("entries_paused"))

    async def save_entries_paused(self, paused: bool) -> None:
        await self._collection().update_one(
            {},
            {
                "$set": {"entries_paused": paused, "updated_at": datetime.now(UTC)},
                "$setOnInsert": {"_id": generate_id_str()},
            },
            upsert=True,
        )
