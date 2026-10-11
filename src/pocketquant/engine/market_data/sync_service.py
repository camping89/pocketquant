"""Manual and scheduled bar sync for one composite symbol: fetch → filter → align → persist.

The data provider comes from the symbol's ``SyncPolicy``; a symbol whose exchange has no
policy returns an error response without touching ``sync_status``.
"""

import asyncio
import time
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from pocketquant.core.common.constants import (
    INTERVAL_SECONDS,
    LIMIT_TVDATAFEED_MAX_BARS,
    build_bar_cache_key,
)
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import coerce_utc
from pocketquant.core.domain.bar.entities import SOURCE_BULK_SYNC, Bar
from pocketquant.core.domain.bar.services.bar_builder import filter_aligned_bars, is_bar_aligned
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.entities import split_composite
from pocketquant.core.domain.sync_status.services import SyncProgressDecision, SyncProgressTracker
from pocketquant.core.infra.persistence import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.engine.market_data.sync_policy import SyncPolicies

logger = get_logger(__name__)

# Aggressive retry: the +2s cron offset in sync_runner removes the bar-close race, so retries
# only absorb residual provider hiccups.
_BACKOFF_SECONDS = (0, 3, 8)
_TIME_BUDGET_SECONDS = 15

# ERROR fires once when the no-progress streak crosses 3× cadence; later stucks stay at WARN
# to avoid alert fatigue during long provider outages.
_STUCK_STREAK_THRESHOLD = 3


class SyncSymbolCommand(BaseModel):
    """Sync historical OHLCV data for a single composite symbol.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    symbol: str = Field(..., description="Composite symbol (e.g., BTCUSDT:BINANCE)")
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )
    skip_filter: bool = Field(
        default=False,
        description="Bypass _filter_new_bars — used by repair to fill gaps",
    )
    source: str = Field(
        ...,
        description="Audit label identifying write path (rest_sync_1m, rest_backfill, ...).",
    )


class BulkSyncCommand(BaseModel):
    """Sync multiple composite symbols in sequence.

    Each entry in ``symbols`` must be a composite ``{code}:{exchange}`` string
    (e.g. ``"BTCUSDT:BINANCE"``).
    """

    symbols: list[str] = Field(
        ...,
        description="List of composite symbol strings, e.g. ['BTCUSDT:BINANCE']",
        examples=[["BTCUSDT:BINANCE", "ETHUSDT:BINANCE"]],
    )
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )


class SyncResponse(BaseModel):
    """Result of sync operation. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    status: str
    bars_synced: int = 0
    # Raw fetch count from provider (before filters).
    bars_fetched: int = 0
    # Bars dropped because they already exist in DB.
    filtered_existing: int = 0
    # Bars dropped because timestamps don't align to the interval grid.
    filtered_misaligned: int = 0
    total_bars: int | None = None
    last_bar_at: str | None = None
    message: str | None = None


async def fetch_with_retry(
    provider: IDataProvider,
    symbol: str,
    interval: Interval,
    n_bars: int,
) -> tuple[list[Bar], int]:
    """Fetch bars; retry on an empty or all-misaligned response.

    The provider may return ``[]`` or the in-progress bar at the exact bar-close moment.
    Returns ``(records, attempts)``; ``records`` is the last attempt's raw output.
    """
    deadline = time.monotonic() + _TIME_BUDGET_SECONDS
    records: list[Bar] = []
    attempt = 0

    for attempt, delay in enumerate(_BACKOFF_SECONDS, start=1):
        if delay:
            if time.monotonic() + delay > deadline:
                # Roll attempt back so caller sees the actual count tried.
                attempt -= 1
                break
            await asyncio.sleep(delay)

        records = await provider.fetch_ohlcv(
            symbol=symbol,
            interval=interval,
            n_bars=n_bars,
        )

        if records and any(
            b.datetime is not None and is_bar_aligned(b.datetime, interval) for b in records
        ):
            if attempt > 1:
                logger.info(
                    "market_data.sync.fetch_recovered",
                    symbol=symbol,
                    interval=interval.value,
                    attempt=attempt,
                    fetched=len(records),
                )
            return records, attempt

    return records, attempt


async def filter_new_bars(
    records: list[Bar],
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
) -> list[Bar]:
    """Drop records whose datetime already exists in DB for this key.

    Queries existing datetimes within [min(records.dt), max(records.dt)] via an indexed
    range scan, so scattered holes get filled. Bars with ``datetime=None`` pass through
    (``drop_misaligned_bars`` handles them).
    """
    if not records:
        return records

    times = [r.datetime for r in records if r.datetime is not None]
    if not times:
        return records

    existing_docs = await bar_repo.find_datetimes(
        symbol,
        interval,
        start_date=min(times),
        end_date=max(times),
    )
    # Mongo client is not tz_aware; raw projection returns naive datetimes.
    # Coerce both sides to tz-aware UTC for set membership equivalence.
    existing_set = {coerce_utc(d["datetime"]) for d in existing_docs}

    filtered = [
        r for r in records if r.datetime is None or coerce_utc(r.datetime) not in existing_set
    ]
    skipped = len(records) - len(filtered)
    if skipped > 0:
        logger.info(
            "market_data.sync.filtered_existing",
            kept=len(filtered),
            skipped=skipped,
            existing_count=len(existing_set),
        )
    return filtered


def drop_misaligned_bars(records: list[Bar], interval: Interval) -> list[Bar]:
    """Drop bars whose timestamps don't align to the interval grid."""
    aligned, misaligned = filter_aligned_bars(records, interval)
    if misaligned:
        logger.warning(
            "market_data.sync.misaligned_bars_dropped",
            count=len(misaligned),
            interval=interval.value,
            sample_times=[str(b.datetime) for b in misaligned[:3]],
        )
    return aligned


def emit_no_progress(
    symbol: str,
    interval: Interval,
    *,
    bars_fetched: int,
    filtered_misaligned: int,
    filtered_existing: int,
    attempts: int,
    streak: int,
    latest_bar: Bar | None,
) -> None:
    """Emit the anomaly log for a no-progress sync (inserted == 0 with existing data)."""
    cadence = INTERVAL_SECONDS.get(interval.value, 0)
    age_s = (
        int((datetime.now(UTC) - latest_bar.datetime).total_seconds())
        if latest_bar and latest_bar.datetime
        else None
    )
    payload: dict[str, object] = {
        "symbol": symbol,
        "interval": interval.value,
        "bars_fetched": bars_fetched,
        "filtered_misaligned": filtered_misaligned,
        "filtered_existing": filtered_existing,
        "attempts": attempts,
        "no_progress_streak": streak,
        "last_bar_age_seconds": age_s,
        "cadence_seconds": cadence,
    }
    crossed_threshold = (
        streak == _STUCK_STREAK_THRESHOLD
        and cadence
        and age_s is not None
        and age_s > _STUCK_STREAK_THRESHOLD * cadence
    )
    if crossed_threshold:
        logger.error("market_data.sync.stuck_threshold_crossed", **payload)
    else:
        logger.warning("market_data.sync.no_progress", **payload)


class SyncService:
    def __init__(
        self,
        policies: SyncPolicies,
        cache: Cache,
        bar_repository: BarRepository,
        symbol_repository: SymbolRepository,
        sync_status_repository: SyncStatusRepository,
    ) -> None:
        self._policies = policies
        self._cache = cache
        self._bar_repo = bar_repository
        self._symbol_repo = symbol_repository
        self._sync_status_repo = sync_status_repository

    async def sync_one(self, request: SyncSymbolCommand) -> SyncResponse:
        """Sync OHLCV bars for a single composite symbol."""
        symbol = request.symbol.upper()
        interval = request.interval
        policy = self._policies.policy_for(symbol)
        if policy is None:
            return SyncResponse(
                symbol=symbol,
                interval=interval.value,
                status="error",
                message=f"no data provider for exchange {split_composite(symbol)[1]}",
                bars_synced=0,
            )

        logger.info(
            "market_data.sync.started",
            symbol=symbol,
            interval=interval.value,
            source=request.source,
        )

        await self._sync_status_repo.upsert(symbol, interval, "syncing")

        try:
            return await self._sync_with(policy.data_provider, symbol, request)
        except Exception as e:
            logger.error(
                "market_data.sync.failed",
                symbol=symbol,
                interval=interval.value,
                error=str(e),
            )
            return await self._fail(symbol, interval, str(e))

    async def sync_bulk(self, request: BulkSyncCommand) -> list[SyncResponse]:
        """Sync multiple composite symbols sequentially."""
        results: list[SyncResponse] = []
        for symbol in request.symbols:
            sync_cmd = SyncSymbolCommand(
                symbol=symbol,
                interval=request.interval,
                n_bars=request.n_bars,
                source=SOURCE_BULK_SYNC,
            )
            result = await self.sync_one(sync_cmd)
            results.append(result)
        return results

    async def _sync_with(
        self, provider: IDataProvider, symbol: str, request: SyncSymbolCommand
    ) -> SyncResponse:
        interval = request.interval
        records, fetch_attempts = await fetch_with_retry(provider, symbol, interval, request.n_bars)
        bars_fetched = len(records)
        filtered_existing = filtered_misaligned = 0

        if records:
            # skip_filter=True on repair runs — gaps must fill regardless of existing state.
            if not request.skip_filter:
                pre = len(records)
                records = await filter_new_bars(records, symbol, interval, self._bar_repo)
                filtered_existing = pre - len(records)
            pre_align = len(records)
            records = drop_misaligned_bars(records, interval)
            filtered_misaligned = pre_align - len(records)

        inserted_count = 0
        if records:
            inserted_count = await self._bar_repo.insert_many(records, source=request.source)
            await self._symbol_repo.upsert(Symbol.create(symbol=symbol))
        total_bars = await self._bar_repo.count(symbol, interval)
        latest_bar = await self._bar_repo.get_latest(symbol, interval)

        if bars_fetched == 0 and total_bars == 0:
            return await self._fail(symbol, interval, "No data returned from provider")

        await self._sync_status_repo.upsert(
            symbol,
            interval,
            "completed",
            bar_count=total_bars,
            last_bar_at=latest_bar.datetime if latest_bar else None,
        )
        await self._cache.delete_pattern(f"{build_bar_cache_key(symbol, interval.value)}:*")
        await self._record_progress(
            symbol,
            interval,
            inserted=inserted_count,
            bars_fetched=bars_fetched,
            filtered_misaligned=filtered_misaligned,
            filtered_existing=filtered_existing,
            attempts=fetch_attempts,
            latest_bar=latest_bar,
        )

        return SyncResponse(
            symbol=symbol,
            interval=interval.value,
            status="completed",
            bars_synced=inserted_count,
            bars_fetched=bars_fetched,
            filtered_existing=filtered_existing,
            filtered_misaligned=filtered_misaligned,
            total_bars=total_bars,
            last_bar_at=(
                latest_bar.datetime.isoformat() if latest_bar and latest_bar.datetime else None
            ),
        )

    async def _record_progress(
        self,
        symbol: str,
        interval: Interval,
        *,
        inserted: int,
        bars_fetched: int,
        filtered_misaligned: int,
        filtered_existing: int,
        attempts: int,
        latest_bar: Bar | None,
    ) -> None:
        decision = SyncProgressTracker.decide(inserted)
        if decision is SyncProgressDecision.RESET:
            await self._sync_status_repo.reset_empty_fetch(symbol, interval)
            logger.info(
                "market_data.sync.completed",
                symbol=symbol,
                bars_inserted=inserted,
            )
            return
        streak = await self._sync_status_repo.bump_empty_fetch(symbol, interval)
        emit_no_progress(
            symbol,
            interval,
            bars_fetched=bars_fetched,
            filtered_misaligned=filtered_misaligned,
            filtered_existing=filtered_existing,
            attempts=attempts,
            streak=streak,
            latest_bar=latest_bar,
        )

    async def _fail(self, symbol: str, interval: Interval, message: str) -> SyncResponse:
        await self._sync_status_repo.upsert(symbol, interval, "error", error_message=message)
        return SyncResponse(
            symbol=symbol,
            interval=interval.value,
            status="error",
            message=message,
            bars_synced=0,
        )
