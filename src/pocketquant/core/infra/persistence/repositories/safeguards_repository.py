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
        await self._save({"entries_paused": paused})

    # The trader's EXNESS_LIVE_TRADING, written at takeover, for display and the
    # subscription create check only. No order path reads it.
    async def load_live_trading(self) -> bool:
        doc = await self._collection().find_one({})
        return bool(doc and doc.get("live_trading"))

    async def save_live_trading(self, live: bool) -> None:
        await self._save({"live_trading": live})

    async def _save(self, fields: dict[str, bool]) -> None:
        await self._collection().update_one(
            {},
            {
                "$set": fields | {"updated_at": datetime.now(UTC)},
                "$setOnInsert": {"_id": generate_id_str()},
            },
            upsert=True,
        )
