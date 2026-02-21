"""Shared bootstrap for testscripts.

Wires only DB + Cache + Mediator + Repos + TradingView provider.
Skips scheduler, broker, strategy engine — keeps it lightweight for debugging.

Usage:
    from _bootstrap import bootstrap, teardown
    ctx = await bootstrap()
    # ... use ctx.mediator, ctx.ohlcv_repo, etc.
    await teardown(ctx)
"""

from types import SimpleNamespace

from src.common.logging import setup_logging
from src.common.mediator.handler_registry import HandlerRegistry
from src.common.mediator.mediator import Mediator
from src.common.messaging import EventBus
from src.config import get_settings
from src.infrastructure.tradingview import TradingViewProvider
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository

# Import handlers to register
from src.features.market_data.sync.sync_one.handler import SyncSymbolHandler


async def bootstrap() -> SimpleNamespace:
    """Connect DB + Cache, wire repos + handlers. Returns namespace with all deps."""
    settings = get_settings()
    setup_logging(settings)

    db = Database()
    await db.connect(settings)

    cache = Cache()
    await cache.connect(settings)

    event_bus = EventBus(max_history=100)
    mediator = Mediator()

    # Repositories
    ohlcv_repo = OHLCVRepository(db)
    symbol_repo = SymbolRepository(db)
    sync_status_repo = SyncStatusRepository(db)

    # TradingView data provider
    tv_provider = TradingViewProvider(settings)

    # Wire sync handler (the main one for market data sync)
    sync_handler = SyncSymbolHandler(
        tv_provider, event_bus, cache, ohlcv_repo, symbol_repo, sync_status_repo
    )

    # Register with mediator so mediator.send(SyncSymbolCommand(...)) works
    registry = HandlerRegistry()
    registry.register_all(mediator, [sync_handler])

    return SimpleNamespace(
        settings=settings,
        db=db,
        cache=cache,
        event_bus=event_bus,
        mediator=mediator,
        tv_provider=tv_provider,
        ohlcv_repo=ohlcv_repo,
        symbol_repo=symbol_repo,
        sync_status_repo=sync_status_repo,
        sync_handler=sync_handler,
    )


async def teardown(ctx: SimpleNamespace) -> None:
    """Disconnect DB + Cache."""
    await ctx.cache.disconnect()
    await ctx.db.disconnect()
