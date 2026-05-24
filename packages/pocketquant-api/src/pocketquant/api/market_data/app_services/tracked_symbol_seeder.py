"""Auto-seed tracked_symbols from existing strategies and open orders on startup.

Idempotent: safe to run on every restart. Uses upsert — no duplicates created.
Logs 'tracked_symbols.seed_completed count=N' for observability.

Legacy documents may store separate ``symbol`` + ``exchange`` fields or a
composite ``symbol`` field (``{code}:{exchange}``). This seeder normalises both
shapes to composite before upserting into tracked_symbols.
"""

from dishka import AsyncContainer
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import utc_now
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger(__name__)

# Orders in these statuses indicate active live interest — include in seed
_OPEN_ORDER_STATUSES = ["open", "partially_filled"]


def _to_composite(doc: dict) -> str | None:
    """Extract composite symbol from a mongo document.

    Handles two shapes:
    - New shape: ``symbol`` already composite ``{code}:{exchange}``
    - Old shape: separate ``symbol`` (code) + ``exchange`` fields

    Returns None if neither shape provides enough data.
    """
    raw_symbol = doc.get("symbol", "")
    if raw_symbol and ":" in raw_symbol:
        # Already composite
        return raw_symbol.upper()
    exchange = doc.get("exchange", "")
    if raw_symbol and exchange:
        return f"{raw_symbol.upper()}:{exchange.upper()}"
    return None


async def seed_tracked_symbols(container: AsyncContainer) -> None:
    """Derive composite symbols from strategies + open orders, upsert all.

    Sources:
    - strategies collection: any status (all loaded strategies need live data)
    - orders collection: status IN ['open', 'partially_filled'] (active orders only)
    """
    database: Database = await container.get(Database)
    repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)

    symbols: set[str] = set()

    # Collect from strategies (all statuses)
    strat_collection = database.get_collection("strategies")
    async for doc in strat_collection.find({}, {"symbol": 1, "exchange": 1}):
        composite = _to_composite(doc)
        if composite:
            symbols.add(composite)

    # Collect from orders (open statuses only)
    orders_collection = database.get_collection("orders")
    async for doc in orders_collection.find(
        {"status": {"$in": _OPEN_ORDER_STATUSES}},
        {"symbol": 1, "exchange": 1},
    ):
        composite = _to_composite(doc)
        if composite:
            symbols.add(composite)

    # Upsert all discovered composite symbols
    now = utc_now()
    for composite in symbols:
        ts = TrackedSymbol(
            symbol=composite,
            created_at=now,
            seeded_from="auto-seed",
        )
        await repo.upsert(ts)

    logger.info(
        "tracked_symbols.seed_completed",
        count=len(symbols),
        source="strategies|orders",
    )
