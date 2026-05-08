"""Auto-seed tracked_symbols from existing strategies and open orders on startup.

Idempotent: safe to run on every restart. Uses upsert — no duplicates created.
Logs 'tracked_symbols.seed_completed count=N' for observability.
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


async def seed_tracked_symbols(container: AsyncContainer) -> None:
    """Derive distinct (exchange, symbol) pairs from strategies + open orders, upsert all.

    Sources:
    - strategies collection: any status (all loaded strategies need live data)
    - orders collection: status IN ['open', 'partially_filled'] (active orders only)
    """
    database: Database = await container.get(Database)
    repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)

    pairs: set[tuple[str, str]] = set()

    # Collect from strategies (all statuses)
    strat_collection = database.get_collection("strategies")
    async for doc in strat_collection.find({}, {"symbol": 1, "exchange": 1}):
        symbol = doc.get("symbol")
        exchange = doc.get("exchange")
        if symbol and exchange:
            pairs.add((exchange.upper(), symbol.upper()))

    # Collect from orders (open statuses only)
    orders_collection = database.get_collection("orders")
    async for doc in orders_collection.find(
        {"status": {"$in": _OPEN_ORDER_STATUSES}},
        {"symbol": 1, "exchange": 1},
    ):
        symbol = doc.get("symbol")
        exchange = doc.get("exchange")
        if symbol and exchange:
            pairs.add((exchange.upper(), symbol.upper()))

    # Upsert all discovered pairs
    now = utc_now()
    for exchange, symbol in pairs:
        ts = TrackedSymbol(
            exchange=exchange,
            symbol=symbol,
            created_at=now,
            seeded_from="auto-seed",
        )
        await repo.upsert(ts)

    logger.info(
        "tracked_symbols.seed_completed",
        count=len(pairs),
        source="strategies|orders",
    )
