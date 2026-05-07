"""Background sync jobs for market data — single 1m REST fetch + cascade aggregation.

sync_1m runs every minute: fetches last 100 1m bars per tracked symbol via REST,
upserts to MongoDB, then cascade-aggregates 1m → 5m/15m/1h/4h/1d (math, no extra
API calls). Sole MongoDB writer for `bars` collection across all timeframes.

sync_verify_cascade runs hourly: picks one sample tracked symbol round-robin,
fetches REST 5m bars, compares with cascade-computed 5m, logs divergence alerts.

All job entrypoints are module-level coroutines so APScheduler can serialize them
as text references for MongoDBJobStore. Dependencies (mediator, repos) are resolved
at job-execution time from a module-level container reference set by
`register_sync_jobs`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pocketquant.api.market_data.app_services.cascade_aggregator import cascade_for_symbol
from pocketquant.api.market_data.app_services.integrity_jobs import (
    check_integrity,
    repair_integrity,
)
from pocketquant.api.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infrastructure.scheduling.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.core.infrastructure.tradingview import TradingViewClient
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)

# All timeframes synced / integrity-checked: 1m via REST, 5m–1d via cascade.
SYNC_INTERVALS = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]

# ---------------------------------------------------------------------------
# Module-level container reference. Set once at startup by register_sync_jobs.
# Job functions resolve their dependencies via this container at execution time.
# ---------------------------------------------------------------------------

_container: AsyncContainer | None = None

# Round-robin counter for sync_verify_cascade symbol selection.
_verify_cascade_counter: int = 0


def set_container(container: AsyncContainer) -> None:
    global _container
    _container = container


def _get_container() -> AsyncContainer:
    if _container is None:
        raise RuntimeError(
            "sync_jobs container not initialized. "
            "Call set_container() before scheduler executes any job."
        )
    return _container


def _ms_since(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


# ---------------------------------------------------------------------------
# Internal sync engine — shared by all interval-based jobs
# ---------------------------------------------------------------------------


async def _sync_by_intervals(
    intervals: list[Interval],
    n_bars: int,
    job_name: str,
    mediator: Mediator,
    tracked_symbol_repo: TrackedSymbolRepository,
    history_repo: JobHistoryRepository,
    doc_id: str | None,
) -> tuple[int, int]:
    """For each tracked symbol, sync the given intervals via REST provider.

    Returns (total_inserted, total_fetched) rolled up across all sub-syncs.
    Symbol source is TrackedSymbolRepository (replaces old SyncStatusRepository scan).
    """
    logger.info(f"market_data.{job_name}.started")

    tracked = await tracked_symbol_repo.list_all()
    symbols = [(ts.symbol, ts.exchange) for ts in tracked]

    if not symbols:
        logger.warning(
            f"market_data.{job_name}.skipped", reason="no_tracked_symbols",
        )
        return 0, 0

    synced = 0
    errors = 0
    first_error: Exception | None = None
    total_inserted = 0
    total_fetched = 0

    for symbol, exchange in symbols:
        for interval in intervals:
            try:
                command = SyncSymbolCommand(
                    symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars,
                )
                result = await mediator.send(command)
                total_inserted += result.bars_synced
                total_fetched += result.bars_fetched
                if doc_id:
                    try:
                        await history_repo.record_detail(
                            doc_id,
                            symbol=symbol,
                            exchange=exchange,
                            interval=interval.value,
                            bars_fetched=result.bars_fetched,
                            bars_inserted=result.bars_synced,
                            filtered_existing=result.filtered_existing,
                            filtered_misaligned=result.filtered_misaligned,
                            status=result.status,
                            error=result.message,
                        )
                    except Exception:
                        logger.warning(
                            "job_history.record_detail_failed",
                            job_id=job_name,
                            exc_info=True,
                        )
                if result.status == "completed":
                    synced += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error(
                    f"market_data.{job_name}.symbol_failed",
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval.value,
                    error=str(e),
                )
                errors += 1
                first_error = first_error or e
                if doc_id:
                    try:
                        await history_repo.record_detail(
                            doc_id,
                            symbol=symbol,
                            exchange=exchange,
                            interval=interval.value,
                            bars_fetched=0,
                            bars_inserted=0,
                            filtered_existing=0,
                            filtered_misaligned=0,
                            status="error",
                            error=str(e),
                        )
                    except Exception:
                        logger.warning(
                            "job_history.record_detail_failed",
                            job_id=job_name,
                            exc_info=True,
                        )

    logger.info(f"market_data.{job_name}.completed", synced_count=synced, error_count=errors)
    if first_error:
        raise first_error
    return total_inserted, total_fetched


# ---------------------------------------------------------------------------
# Job runners — wrap actual work with history recording.
# ---------------------------------------------------------------------------


async def _run_sync(name: str, intervals: list[Interval], n_bars: int) -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    mediator = await container.get(Mediator)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)

    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        total_inserted, total_fetched = await _sync_by_intervals(
            intervals, n_bars, name, mediator, tracked_symbol_repo, history_repo, doc_id,
        )
        if doc_id:
            await history_repo.record_finish(
                doc_id,
                status="completed",
                duration_ms=_ms_since(started),
                total_inserted=total_inserted,
                total_fetched=total_fetched,
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


async def _run_integrity(name: str) -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)

    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        tracked = await tracked_symbol_repo.list_all()
        symbols = [(ts.symbol, ts.exchange) for ts in tracked]
        for symbol, exchange in symbols:
            for interval in SYNC_INTERVALS:
                report = await check_integrity(symbol, exchange, interval, bar_repo)
                if report["misaligned_count"] or report["missing_count"]:
                    logger.warning(
                        "integrity.issues_found",
                        symbol=symbol, exchange=exchange, interval=interval.value,
                        misaligned=report["misaligned_count"],
                        missing=report["missing_count"],
                    )
        if doc_id:
            await history_repo.record_finish(
                doc_id, status="completed", duration_ms=_ms_since(started)
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


async def _run_repair(name: str) -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    mediator = await container.get(Mediator)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)

    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        tracked = await tracked_symbol_repo.list_all()
        symbols = [(ts.symbol, ts.exchange) for ts in tracked]
        for symbol, exchange in symbols:
            for interval in SYNC_INTERVALS:
                result = await repair_integrity(
                    symbol, exchange, interval, bar_repo, mediator
                )
                if result["deleted"] or result["gaps_resynced"]:
                    logger.info(
                        "integrity.repaired",
                        symbol=symbol, exchange=exchange, interval=interval.value,
                        deleted=result["deleted"],
                        gaps_resynced=result["gaps_resynced"],
                    )
        if doc_id:
            await history_repo.record_finish(
                doc_id, status="completed", duration_ms=_ms_since(started)
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


# ---------------------------------------------------------------------------
# Picklable job entrypoints — referenced by APScheduler as
# "pocketquant.api.market_data.app_services.sync_jobs:<funcname>"
# ---------------------------------------------------------------------------


async def sync_1m() -> None:
    """Fetch last 100 1m bars per tracked symbol, upsert, then cascade to 5m–1d."""
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    mediator = await container.get(Mediator)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)

    name = "sync_1m"
    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        # Step 1: REST-fetch 1m bars for all tracked symbols and upsert to Mongo.
        total_inserted, total_fetched = await _sync_by_intervals(
            [Interval.MINUTE_1], 100, name, mediator, tracked_symbol_repo, history_repo, doc_id,
        )

        # Step 2: Cascade 1m → 5m/15m/1h/4h/1d for each tracked symbol.
        tracked = await tracked_symbol_repo.list_all()
        cascade_total: dict[Interval, int] = {}
        for ts in tracked:
            try:
                counts = await cascade_for_symbol(
                    ts.symbol, ts.exchange, lookback_minutes=100, bar_repo=bar_repo,
                )
                for tf, count in counts.items():
                    cascade_total[tf] = cascade_total.get(tf, 0) + count
            except Exception:
                logger.error(
                    "sync_1m.cascade_failed",
                    symbol=ts.symbol,
                    exchange=ts.exchange,
                    exc_info=True,
                )

        logger.info(
            "sync_1m.cascade_summary",
            cascade_counts={tf.value: n for tf, n in cascade_total.items()},
        )

        if doc_id:
            await history_repo.record_finish(
                doc_id,
                status="completed",
                duration_ms=_ms_since(started),
                total_inserted=total_inserted,
                total_fetched=total_fetched,
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


async def sync_verify_cascade() -> None:
    """Hourly sanity check: compare cascade 5m bars vs REST get_hist(5m, n=12).

    Picks one tracked symbol per run (round-robin). Logs divergence_alert if
    abs(rest.close - cascade.close) > 0.01 for >5% of the 12 comparison bars.
    """
    global _verify_cascade_counter

    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    provider = await container.get(TradingViewClient)

    name = "sync_verify_cascade"
    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        tracked = await tracked_symbol_repo.list_all()
        if not tracked:
            logger.warning(
                "sync_verify_cascade.skipped", reason="no_tracked_symbols",
            )
            if doc_id:
                await history_repo.record_finish(
                    doc_id, status="completed", duration_ms=_ms_since(started)
                )
            return

        # Round-robin symbol selection.
        idx = _verify_cascade_counter % len(tracked)
        _verify_cascade_counter += 1
        ts = tracked[idx]
        symbol = ts.symbol.upper()
        exchange = ts.exchange.upper()

        logger.info(
            "sync_verify_cascade.started",
            symbol=symbol,
            exchange=exchange,
            sample_idx=idx,
        )

        # Fetch 12 REST 5m bars (last ~1 hour).
        rest_bars = await provider.fetch_ohlcv(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.MINUTE_5,
            n_bars=12,
        )

        if not rest_bars:
            logger.warning("sync_verify_cascade.rest_empty", symbol=symbol, exchange=exchange)
            if doc_id:
                await history_repo.record_finish(
                    doc_id, status="completed", duration_ms=_ms_since(started)
                )
            return

        # Query cascade-computed 5m bars for the same time window.
        oldest_rest = min(b.datetime for b in rest_bars if b.datetime)
        newest_rest = max(b.datetime for b in rest_bars if b.datetime)
        cascade_bars = await bar_repo.find(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.MINUTE_5,
            start_date=oldest_rest,
            end_date=newest_rest + timedelta(minutes=5),
            limit=20,
        )

        if not cascade_bars:
            logger.warning(
                "sync_verify_cascade.cascade_empty",
                symbol=symbol,
                exchange=exchange,
                reason="no_cascade_5m_bars_in_window",
            )
            if doc_id:
                await history_repo.record_finish(
                    doc_id, status="completed", duration_ms=_ms_since(started)
                )
            return

        # Build lookup: cascade bars indexed by datetime for O(1) comparison.
        cascade_by_dt: dict = {b.datetime: b for b in cascade_bars if b.datetime}

        divergence_count = 0
        compared = 0
        for rest_bar in rest_bars:
            if not rest_bar.datetime:
                continue
            cascade_bar = cascade_by_dt.get(rest_bar.datetime)
            if cascade_bar is None:
                continue
            compared += 1
            if abs(rest_bar.close - cascade_bar.close) > 0.01:
                divergence_count += 1

        if compared > 0 and divergence_count / compared > 0.05:
            logger.warning(
                "cascade.divergence_alert",
                symbol=symbol,
                exchange=exchange,
                divergence_count=divergence_count,
                compared=compared,
                threshold_pct=5,
            )
        else:
            logger.info(
                "sync_verify_cascade.ok",
                symbol=symbol,
                exchange=exchange,
                compared=compared,
                divergence_count=divergence_count,
            )

        if doc_id:
            await history_repo.record_finish(
                doc_id, status="completed", duration_ms=_ms_since(started)
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


async def sync_backfill() -> None:
    """Daily deep backfill: REST-fetch 5000 bars for all tracked symbols across all tfs."""
    await _run_sync("sync_backfill", SYNC_INTERVALS, 5000)


async def sync_integrity() -> None:
    """Daily integrity scan across all tfs (1m + cascade outputs)."""
    await _run_integrity("sync_integrity")


async def sync_repair() -> None:
    """Bi-daily gap repair across all tfs."""
    await _run_repair("sync_repair")


# ---------------------------------------------------------------------------
# Registration entrypoint
# ---------------------------------------------------------------------------


_MODULE = "pocketquant.api.market_data.app_services.sync_jobs"


def register_sync_jobs(
    container: AsyncContainer,
    job_scheduler: JobScheduler,
) -> None:
    """Wire container reference + register 5 sync/integrity jobs as text refs."""
    set_container(container)

    # UTC wall-clock anchored — bar-aligned crons eliminate phase drift on restart.
    # Strategy correctness depends on bar-close events arriving on time; lag/gaps
    # cause missed entries/exits. See debug-260505-1213-15m-freshness-delay.md.
    #
    # sync_1m runs at +2s from bar close. Gives TradingView time to settle the
    # just-closed bar. Cascade runs in-process after 1m upsert — no extra API calls.
    # coalesce + max_instances=1 are APScheduler defaults — overlap prevention built-in.
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_1m", job_id="sync_1m",
        cron_expression="*/1 * * * *", second=2,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_verify_cascade", job_id="sync_verify_cascade",
        cron_expression="0 * * * *",
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_backfill", job_id="sync_backfill", hour=3, minute=0,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_integrity", job_id="sync_integrity", hour=4, minute=0,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_repair", job_id="sync_repair", cron_expression="0 */12 * * *",
    )

    logger.info("market_data.registered_sync_jobs", job_count=5)
