"""Handler for backfilling historical bars for a tracked symbol.

Two modes:
  direct  — REST-fetch the requested tf directly, upsert to Mongo.
  cascade — REST-fetch 1m bars (n * tf_minutes worth), upsert 1m, then cascade
             to the requested tf and all higher tfs within the lookback window.

The handler is NOT a mediator handler (no @handles decorator) because it needs
direct access to provider + bar_repo + cascade_aggregator and does not fit the
single-command → single-result pattern cleanly. Route calls it directly via DI.
"""

from __future__ import annotations

from pocketquant.api.market_data.app_services.cascade_aggregator import (
    cascade_for_symbol,
    tf_seconds,
)
from pocketquant.api.market_data.handlers.tracked_symbols.backfill.command import (
    BackfillTrackedSymbolCommand,
)
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_TRACKED_SYMBOL_BACKFILL
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infrastructure.data_provider import IDataProvider
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


class BackfillTrackedSymbolHandler:
    """Execute a backfill request for one (exchange, symbol) pair."""

    def __init__(
        self,
        provider: IDataProvider,
        bar_repository: BarRepository,
    ) -> None:
        self._provider = provider
        self._bar_repo = bar_repository

    async def handle(self, cmd: BackfillTrackedSymbolCommand) -> dict:
        """Run backfill. Returns {persisted_count, mode_used}."""
        mode = cmd.resolved_mode()
        symbol = cmd.symbol.upper()
        exchange = cmd.exchange.upper()

        logger.info(
            "backfill.started",
            symbol=symbol,
            exchange=exchange,
            interval=cmd.interval.value,
            n=cmd.n,
            mode=mode,
        )

        if mode == "direct":
            persisted = await self._direct(symbol, exchange, cmd.interval, cmd.n)
        else:
            persisted = await self._cascade(symbol, exchange, cmd.interval, cmd.n)

        logger.info(
            "backfill.completed",
            symbol=symbol,
            exchange=exchange,
            interval=cmd.interval.value,
            mode=mode,
            persisted_count=persisted,
        )
        return {"persisted_count": persisted, "mode_used": mode}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _direct(
        self, symbol: str, exchange: str, interval: Interval, n: int
    ) -> int:
        """REST-fetch the requested tf directly and upsert."""
        bars = await self._provider.fetch_ohlcv(
            symbol=symbol, exchange=exchange, interval=interval, n_bars=n,
        )
        if not bars:
            logger.warning(
                "backfill.direct_empty",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
            )
            return 0

        persisted = 0
        for bar in bars:
            try:
                await self._bar_repo.upsert_bar(bar, source=SOURCE_TRACKED_SYMBOL_BACKFILL)
                persisted += 1
            except Exception:
                logger.error(
                    "backfill.upsert_failed",
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval.value,
                    exc_info=True,
                )
        return persisted

    async def _cascade(
        self, symbol: str, exchange: str, interval: Interval, n: int
    ) -> int:
        """REST-fetch 1m source bars, upsert, then cascade to the requested tf."""
        # How many 1m bars do we need to cover n bars of the target tf?
        tf_secs = tf_seconds(interval)
        tf_minutes = tf_secs // 60
        lookback_minutes = n * tf_minutes

        # Fetch and upsert 1m bars (the source-of-truth).
        bars_1m = await self._provider.fetch_ohlcv(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.MINUTE_1,
            n_bars=min(lookback_minutes + 10, 5000),  # headroom; cap at provider limit
        )
        if not bars_1m:
            logger.warning(
                "backfill.cascade_1m_empty",
                symbol=symbol,
                exchange=exchange,
                target_tf=interval.value,
            )
            return 0

        for bar in bars_1m:
            try:
                await self._bar_repo.upsert_bar(bar, source=SOURCE_TRACKED_SYMBOL_BACKFILL)
            except Exception:
                logger.error(
                    "backfill.cascade_1m_upsert_failed",
                    symbol=symbol,
                    exchange=exchange,
                    exc_info=True,
                )

        # Cascade from 1m → all higher tfs within the lookback window.
        counts = await cascade_for_symbol(
            symbol=symbol,
            exchange=exchange,
            lookback_minutes=lookback_minutes,
            bar_repo=self._bar_repo,
        )

        # Return the count for the specifically requested tf (or total if 1m).
        return counts.get(interval, 0)
