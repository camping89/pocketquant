"""tracked_symbols feature service — CRUD on the tracked composite-symbol list.

Removing a symbol cascades to every document and cache key that references it.
Request DTOs keep their original class names so OpenAPI schema components
stay stable (routes expose them as request bodies).
"""

from pydantic import BaseModel, Field, field_validator

from pocketquant.core.common.constants import (
    CACHE_KEY_BAR_CURRENT,
    CACHE_KEY_DATA_LAG,
    CACHE_KEY_OHLCV,
    CACHE_KEY_QUOTE_LATEST,
)
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import utc_now
from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_PATTERN
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.base_repository import SymbolScopedRepository
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.engine.strategy.strategy_command_service import StrategyCommandService

logger = get_logger(__name__)


class AddTrackedSymbolCommand(BaseModel):
    """Add composite ``{code}:{exchange}`` symbol to tracked_symbols. Idempotent — 200 if exists."""

    symbol: str = Field(
        ...,
        min_length=3,
        max_length=65,
        description="Composite symbol e.g. BTCUSDT:BINANCE",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not COMPOSITE_SYMBOL_PATTERN.match(v):
            raise ValueError("Must be composite {CODE}:{EXCHANGE} format")
        return v


class TrackedSymbolService:
    """CRUD on tracked_symbols; ``remove`` cascades to all data of the symbol."""

    def __init__(
        self,
        tracked_symbol_repository: TrackedSymbolRepository,
        symbol_repository: SymbolRepository,
        bar_repository: BarRepository,
        sync_status_repository: SyncStatusRepository,
        subscription_repository: SubscriptionRepository,
        strategy_command_service: StrategyCommandService,
        backtest_repository: BacktestRepository,
        backtest_order_repository: BacktestOrderRepository,
        backtest_trade_repository: BacktestTradeRepository,
        order_repository: OrderRepository,
        position_repository: PositionRepository,
        trade_repository: TradeRepository,
        job_history_repository: JobHistoryRepository,
        cache: Cache,
    ) -> None:
        self._repo = tracked_symbol_repository
        self._sub_repo = subscription_repository
        self._strategy_commands = strategy_command_service
        self._job_history_repo = job_history_repository
        self._cache = cache
        # Backtest orders/trades go before their runs so a crash mid-cascade
        # still leaves the runs findable by symbol on retry.
        self._symbol_data: dict[str, SymbolScopedRepository] = {
            "symbols": symbol_repository,
            "bars": bar_repository,
            "sync_status": sync_status_repository,
            "backtest_orders": backtest_order_repository,
            "backtest_trades": backtest_trade_repository,
            "backtest_runs": backtest_repository,
            "orders": order_repository,
            "positions": position_repository,
            "trades": trade_repository,
        }

    async def add(self, request: AddTrackedSymbolCommand) -> dict:
        """Upsert composite symbol into tracked_symbols. Returns current state."""
        ts = TrackedSymbol(
            symbol=request.symbol,
            created_at=utc_now(),
            seeded_from="admin",
        )
        await self._repo.upsert(ts)
        logger.info("tracked_symbols.added", symbol=request.symbol)
        return {
            "symbol": ts.symbol,
            "created_at": ts.created_at.isoformat(),
            "seeded_from": ts.seeded_from,
        }

    async def update(self, symbol: str) -> dict:
        # Currently no mutable metadata beyond the composite symbol itself —
        # update is a no-op placeholder that validates existence.
        found = await self._repo.update(symbol, {})
        if not found:
            raise NotFoundError(
                f"Tracked symbol '{symbol}' not found",
                error_code="TRACKED_SYMBOL_NOT_FOUND",
            )
        logger.info("tracked_symbols.updated", symbol=symbol)
        return {"symbol": symbol, "status": "updated"}

    async def remove(self, symbol: str) -> dict:
        """Delete the symbol and every document and cache key that references it.

        Idempotent: each step deletes whatever is left, so a retry after a
        partial run (or on an already-removed symbol) finishes the cleanup and
        reports 0 for steps already done. tracked_symbols goes first so sync
        jobs and the quote feed stop producing data for the symbol; each
        subscription is stopped, then removed through the strategy command path.
        Returns per-collection deleted counts under ``deleted``.
        """
        deleted = {"tracked_symbols": await self._repo.delete_by_symbol(symbol)}
        deleted["subscriptions"] = 0
        for sub in await self._sub_repo.list_by_symbol(symbol):
            sub_id = str(sub.id)
            await self._strategy_commands.stop(sub_id)
            deleted["subscriptions"] += await self._strategy_commands.remove_symbol(sub_id)
        for name, repo in self._symbol_data.items():
            deleted[name] = await repo.delete_by_symbol(symbol)
        deleted["job_history_runs"] = await self._job_history_repo.remove_symbol_details(symbol)
        patterns = (
            CACHE_KEY_QUOTE_LATEST.format(symbol=symbol),
            CACHE_KEY_BAR_CURRENT.format(symbol=symbol, interval="*"),
            CACHE_KEY_OHLCV.format(symbol=symbol, interval="*", limit="*"),
            CACHE_KEY_DATA_LAG.format(symbol=symbol),
        )
        deleted["cache_keys"] = 0
        for pattern in patterns:
            deleted["cache_keys"] += await self._cache.delete_pattern(pattern)
        logger.info("tracked_symbols.removed", symbol=symbol, deleted=deleted)
        return {"symbol": symbol, "status": "removed", "deleted": deleted}

    async def list_all(self) -> list[dict]:
        """Return all tracked composite symbols."""
        symbols = await self._repo.list_all()
        return [
            {
                "symbol": ts.symbol,
                "created_at": ts.created_at.isoformat(),
                "seeded_from": ts.seeded_from,
            }
            for ts in symbols
        ]
