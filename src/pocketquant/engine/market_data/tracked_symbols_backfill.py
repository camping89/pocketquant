"""Backfill historical bars for a tracked symbol.

Two modes:
  direct  — REST-fetch the requested tf directly, upsert to Mongo.
  cascade — REST-fetch 1m bars (n * tf_minutes worth), upsert 1m, then cascade
             to the requested tf and all higher tfs within the lookback window.

Needs direct access to provider + bar_repo + cascade_aggregator — route injects
the service via DI and calls ``run()``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_TRACKED_SYMBOL_BACKFILL
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_PATTERN
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.cascade_aggregator import (
    cascade_for_symbol,
    tf_seconds,
)

logger = get_logger(__name__)


# Intervals that default to cascade mode (derived from 1m source).
_CASCADE_DEFAULT_TFS = {
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
}


class BackfillTrackedSymbolCommand(BaseModel):
    """Backfill historical bars for one composite symbol.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).

    mode=cascade  — REST-fetch 1m bars (n * tf_minutes), upsert, then cascade aggregate.
                    Default for tfs >= 5m.
    mode=direct   — REST-fetch the requested tf directly and upsert.
                    Default for 1m; always used when tf=1m regardless of mode param.
    """

    symbol: str = Field(
        ...,
        min_length=3,
        max_length=65,
        description="Composite symbol e.g. BTCUSDT:BINANCE",
    )
    interval: Interval
    n: int = Field(default=100, ge=1, le=5000, description="Number of bars to backfill")
    mode: str = Field(default="auto", description="cascade | direct | auto")

    @field_validator("symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not COMPOSITE_SYMBOL_PATTERN.match(v):
            raise ValueError("Must be composite {CODE}:{EXCHANGE} format")
        return v

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("cascade", "direct", "auto"):
            raise ValueError("mode must be 'cascade', 'direct', or 'auto'")
        return v

    def resolved_mode(self) -> str:
        if self.mode != "auto":
            return self.mode
        return "cascade" if self.interval in _CASCADE_DEFAULT_TFS else "direct"


class TrackedSymbolBackfillService:
    """Execute a backfill request for one composite symbol."""

    def __init__(
        self,
        provider: IDataProviderPort,
        bar_repository: BarRepository,
    ) -> None:
        self._provider = provider
        self._bar_repo = bar_repository

    async def run(self, cmd: BackfillTrackedSymbolCommand) -> dict:
        mode = cmd.resolved_mode()
        symbol = cmd.symbol.upper()

        logger.info(
            "backfill.started",
            symbol=symbol,
            interval=cmd.interval.value,
            n=cmd.n,
            mode=mode,
        )

        if mode == "direct":
            persisted = await self._direct(symbol, cmd.interval, cmd.n)
        else:
            persisted = await self._cascade(symbol, cmd.interval, cmd.n)

        logger.info(
            "backfill.completed",
            symbol=symbol,
            interval=cmd.interval.value,
            mode=mode,
            persisted_count=persisted,
        )
        return {"persisted_count": persisted, "mode_used": mode}

    async def _direct(self, symbol: str, interval: Interval, n: int) -> int:
        bars = await self._provider.fetch_ohlcv(
            symbol=symbol,
            interval=interval,
            n_bars=n,
        )
        if not bars:
            logger.warning(
                "backfill.direct_empty",
                symbol=symbol,
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
                    interval=interval.value,
                    exc_info=True,
                )
        return persisted

    async def _cascade(self, symbol: str, interval: Interval, n: int) -> int:
        tf_secs = tf_seconds(interval)
        tf_minutes = tf_secs // 60
        lookback_minutes = n * tf_minutes

        bars_1m = await self._provider.fetch_ohlcv(
            symbol=symbol,
            interval=Interval.MINUTE_1,
            n_bars=min(lookback_minutes + 10, 5000),  # headroom; cap at provider limit
        )
        if not bars_1m:
            logger.warning(
                "backfill.cascade_1m_empty",
                symbol=symbol,
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
                    exc_info=True,
                )

        counts = await cascade_for_symbol(
            symbol=symbol,
            lookback_minutes=lookback_minutes,
            bar_repo=self._bar_repo,
        )

        return counts.get(interval, 0)
