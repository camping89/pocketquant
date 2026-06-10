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

``symbol`` is composite ``{code}:{exchange}`` throughout — no separate exchange param.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.bar.entities import (
    SOURCE_REST_BACKFILL,
    SOURCE_REST_REPAIR,
    SOURCE_REST_SYNC_1M,
)
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.market_data.app_services.cascade_aggregator import cascade_for_symbol
from pocketquant.engine.market_data.app_services.integrity_jobs import (
    check_integrity,
    repair_integrity,
)
from pocketquant.engine.market_data.handlers.sync import SyncSymbolCommand

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

# Catch-up targets — heavy daily/12h jobs that silently drop runs when a restart
# spans their (per-job) misfire_grace_time window. (job_id, func_ref, max_gap_s).
# Excludes sync_1m (cascade lookback heals) and sync_verify_cascade (read-only).
#
# max_gap = expected_interval + per-job grace, e.g. sync_backfill runs every 24h
# with 1h grace → 25h gap means the daily run was definitely missed.
_MODULE = "pocketquant.engine.market_data.app_services.sync_jobs"

CATCHUP_TARGETS: list[tuple[str, str, int]] = [
    ("sync_backfill", f"{_MODULE}:sync_backfill", 86400 + 3600),  # 24h + 1h
    ("sync_integrity", f"{_MODULE}:sync_integrity", 86400 + 3600),
    ("sync_repair", f"{_MODULE}:sync_repair", 43200 + 1800),  # 12h + 30min
]

# Module-level container reference. Set once at startup by register_sync_jobs.
# Job functions resolve their dependencies via this container at execution time.
_container: AsyncContainer | None = None

# Verify cascade thresholds (per-field).
# Price relative threshold catches scale-aware drift across assets:
#   BTC $80k → $8 trigger; ETH $3k → $0.30 trigger.
# Volume gets its own threshold because exchange-side rounding is noisier than price.
# ---------------------------------------------------------------------------
PRICE_THRESHOLD_PCT = 0.0001  # 0.01%
VOLUME_THRESHOLD_PCT = 0.05  # 5%
DIVERGENCE_ALERT_FRACTION = 0.05  # alert when >5% of compared bars diverge on any field


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


def _diff_pct(a: float, b: float) -> float:
    """Relative absolute diff. Returns 0.0 when |a| is too small to divide safely."""
    if abs(a) < 1e-12:
        return 0.0
    return abs(a - b) / abs(a)


def compare_bar_fields(rest_bar, db_bar) -> dict[str, bool]:  # noqa: ANN001
    """Per-field divergence map (True == divergent beyond threshold).

    Pure function to keep `sync_verify_cascade` thin and unit-testable. Price
    fields share PRICE_THRESHOLD_PCT; volume gets its looser VOLUME_THRESHOLD_PCT.
    """
    return {
        "open": _diff_pct(rest_bar.open, db_bar.open) > PRICE_THRESHOLD_PCT,
        "high": _diff_pct(rest_bar.high, db_bar.high) > PRICE_THRESHOLD_PCT,
        "low": _diff_pct(rest_bar.low, db_bar.low) > PRICE_THRESHOLD_PCT,
        "close": _diff_pct(rest_bar.close, db_bar.close) > PRICE_THRESHOLD_PCT,
        "volume": _diff_pct(rest_bar.volume, db_bar.volume) > VOLUME_THRESHOLD_PCT,
    }


async def _sync_by_intervals(
    intervals: list[Interval],
    n_bars: int,
    job_name: str,
    mediator: Mediator,
    tracked_symbol_repo: TrackedSymbolRepository,
    history_repo: JobHistoryRepository,
    doc_id: str | None,
    source: str,
) -> tuple[int, int]:
    """For each tracked symbol, sync the given intervals via REST provider.

    Returns (total_inserted, total_fetched) rolled up across all sub-syncs.
    Symbol source is TrackedSymbolRepository (replaces old SyncStatusRepository scan).
    Each ts.symbol is composite ``{code}:{exchange}``.
    """
    logger.info(f"market_data.{job_name}.started")

    tracked = await tracked_symbol_repo.list_all()
    symbols = [ts.symbol for ts in tracked]

    if not symbols:
        logger.warning(
            f"market_data.{job_name}.skipped",
            reason="no_tracked_symbols",
        )
        return 0, 0

    synced = 0
    errors = 0
    first_error: Exception | None = None
    total_inserted = 0
    total_fetched = 0

    for symbol in symbols:
        for interval in intervals:
            try:
                command = SyncSymbolCommand(
                    symbol=symbol,
                    interval=interval,
                    n_bars=n_bars,
                    source=source,
                )
                result = await mediator.send(command)
                total_inserted += result.bars_synced
                total_fetched += result.bars_fetched
                if doc_id:
                    try:
                        await history_repo.record_detail(
                            doc_id,
                            symbol=symbol,
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


async def _run_sync(
    name: str,
    intervals: list[Interval],
    n_bars: int,
    source: str,
) -> None:
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
            intervals,
            n_bars,
            name,
            mediator,
            tracked_symbol_repo,
            history_repo,
            doc_id,
            source=source,
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
                logger.warning("job_history.record_finish_failed", job_id=name, exc_info=True)
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
        for ts in tracked:
            for interval in SYNC_INTERVALS:
                report = await check_integrity(ts.symbol, interval, bar_repo)
                if report["misaligned_count"] or report["missing_count"]:
                    logger.warning(
                        "integrity.issues_found",
                        symbol=ts.symbol,
                        interval=interval.value,
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
                logger.warning("job_history.record_finish_failed", job_id=name, exc_info=True)
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
        for ts in tracked:
            for interval in SYNC_INTERVALS:
                result = await repair_integrity(
                    ts.symbol,
                    interval,
                    bar_repo,
                    mediator,
                    source=SOURCE_REST_REPAIR,
                )
                if result["deleted"] or result["gaps_resynced"]:
                    logger.info(
                        "integrity.repaired",
                        symbol=ts.symbol,
                        interval=interval.value,
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
                logger.warning("job_history.record_finish_failed", job_id=name, exc_info=True)
        raise


# APScheduler entrypoints — referenced by text as
# "pocketquant.engine.market_data.app_services.sync_jobs:<funcname>"
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
        total_inserted, total_fetched = await _sync_by_intervals(
            [Interval.MINUTE_1],
            100,
            name,
            mediator,
            tracked_symbol_repo,
            history_repo,
            doc_id,
            source=SOURCE_REST_SYNC_1M,
        )

        tracked = await tracked_symbol_repo.list_all()
        cascade_total: dict[Interval, int] = {}
        for ts in tracked:
            try:
                counts = await cascade_for_symbol(
                    ts.symbol,
                    lookback_minutes=100,
                    bar_repo=bar_repo,
                )
                for tf, count in counts.items():
                    cascade_total[tf] = cascade_total.get(tf, 0) + count
            except Exception:
                logger.error(
                    "sync_1m.cascade_failed",
                    symbol=ts.symbol,
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
                logger.warning("job_history.record_finish_failed", job_id=name, exc_info=True)
        raise


async def _verify_one_symbol(
    symbol: str,
    *,
    provider: IDataProvider,
    bar_repo: BarRepository,
) -> dict:
    """Compare REST 5m bars against cascade-stored 5m bars for composite ``symbol``.

    Returns a per-symbol summary dict with compared / divergence_count / sample_divergences.
    Raises on REST/DB failures so the caller can record per-symbol error state.
    """
    rest_bars = await provider.fetch_ohlcv(
        symbol=symbol,
        interval=Interval.MINUTE_5,
        n_bars=12,
    )
    if not rest_bars:
        return {"symbol": symbol, "compared": 0, "rest_empty": True}

    oldest_rest = min(b.datetime for b in rest_bars if b.datetime)
    newest_rest = max(b.datetime for b in rest_bars if b.datetime)
    cascade_bars = await bar_repo.find(
        symbol=symbol,
        interval=Interval.MINUTE_5,
        start_date=oldest_rest,
        end_date=newest_rest + timedelta(minutes=5),
        limit=20,
    )
    if not cascade_bars:
        return {"symbol": symbol, "compared": 0, "cascade_empty": True}

    cascade_by_dt: dict = {b.datetime: b for b in cascade_bars if b.datetime}

    compared = 0
    divergence_count = 0
    samples: list[dict] = []
    for rest_bar in rest_bars:
        if not rest_bar.datetime:
            continue
        cascade_bar = cascade_by_dt.get(rest_bar.datetime)
        if cascade_bar is None:
            continue
        compared += 1
        fields_diff = compare_bar_fields(rest_bar, cascade_bar)
        if any(fields_diff.values()):
            divergence_count += 1
            if len(samples) < 3:
                samples.append({"datetime": rest_bar.datetime.isoformat(), "fields": fields_diff})

    return {
        "symbol": symbol,
        "compared": compared,
        "divergence_count": divergence_count,
        "samples": samples,
    }


async def sync_verify_cascade() -> None:
    """Hourly full-fleet sanity check: REST 5m vs cascade 5m, full OHLCV per field.

    Iterates ALL tracked symbols (no round-robin). Each comparison checks O/H/L/C
    against PRICE_THRESHOLD_PCT and V against VOLUME_THRESHOLD_PCT. Alerts when
    divergence_count/compared > DIVERGENCE_ALERT_FRACTION for that symbol.
    """
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    provider = await container.get(IDataProvider)

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
            logger.warning("sync_verify_cascade.skipped", reason="no_tracked_symbols")
            if doc_id:
                await history_repo.record_finish(
                    doc_id, status="completed", duration_ms=_ms_since(started)
                )
            return

        logger.info("sync_verify_cascade.started", symbols=len(tracked))

        for ts in tracked:
            symbol = ts.symbol.upper()
            try:
                summary = await _verify_one_symbol(
                    symbol,
                    provider=provider,
                    bar_repo=bar_repo,
                )
            except Exception as exc:
                logger.error(
                    "sync_verify_cascade.symbol_failed",
                    symbol=symbol,
                    error=str(exc),
                )
                continue

            if summary.get("rest_empty"):
                logger.warning("sync_verify_cascade.rest_empty", symbol=symbol)
                continue
            if summary.get("cascade_empty"):
                logger.warning(
                    "sync_verify_cascade.cascade_empty",
                    symbol=symbol,
                    reason="no_cascade_5m_bars_in_window",
                )
                continue

            compared = summary["compared"]
            div = summary["divergence_count"]
            if compared > 0 and div / compared > DIVERGENCE_ALERT_FRACTION:
                logger.warning(
                    "cascade.divergence_alert",
                    symbol=symbol,
                    divergence_count=div,
                    compared=compared,
                    price_threshold_pct=PRICE_THRESHOLD_PCT,
                    volume_threshold_pct=VOLUME_THRESHOLD_PCT,
                    sample_divergences=summary["samples"],
                )
            else:
                logger.info(
                    "sync_verify_cascade.ok",
                    symbol=symbol,
                    compared=compared,
                    divergence_count=div,
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
                logger.warning("job_history.record_finish_failed", job_id=name, exc_info=True)
        raise


async def sync_backfill() -> None:
    """Daily deep backfill: REST-fetch 5000 bars for all tracked symbols across all tfs."""
    await _run_sync("sync_backfill", SYNC_INTERVALS, 5000, source=SOURCE_REST_BACKFILL)


async def sync_integrity() -> None:
    """Daily integrity scan across all tfs (1m + cascade outputs)."""
    await _run_integrity("sync_integrity")


async def sync_repair() -> None:
    """Bi-daily gap repair across all tfs."""
    await _run_repair("sync_repair")


async def enqueue_missed_catchups(
    history_repo: JobHistoryRepository,
    job_scheduler: JobScheduler,
) -> None:
    """Enqueue a one-off catch-up run for each CATCHUP_TARGETS job whose last
    success exceeds its per-job ``max_gap``.

    Multi-instance safe: ``add_one_off_job`` uses ``replace_existing=True`` with
    a stable ``_catchup`` suffix, so a simultaneous resolve on VPS + local-dev
    overwrites the first call — only one execution. Fresh DB (``last is None``)
    is treated as "no catch-up needed"; the next cron tick handles the first run.

    Assumes ``scheduler.start()`` has already run by call time (the JobScheduler
    Dishka factory starts the scheduler inside its async-gen yield, which
    completes before ``container.get(JobScheduler)`` returns in the caller). If
    that ever inverts, the one-off persists with ``next_run_time=now`` and fires
    on the first post-start tick — harmlessly deferred, never dropped.

    Note on history-doc naming: the catchup's APScheduler job_id is
    ``<job_id>_catchup``, but the wrapper inside (``_run_sync`` etc.) writes a
    ``job_history`` doc keyed by the ORIGINAL job_id. That's intentional — the
    next boot's ``get_last_successful_started_at(<job_id>)`` then sees the
    recent success and skips re-enqueueing.
    """
    now = datetime.now(UTC)
    for job_id, func_ref, max_gap in CATCHUP_TARGETS:
        last = await history_repo.get_last_successful_started_at(job_id)
        if last is None:
            continue
        gap = (now - last).total_seconds()
        if gap > max_gap:
            job_scheduler.add_one_off_job(
                func_ref,
                job_id=f"{job_id}_catchup",
            )
            logger.info(
                "scheduler.catchup_enqueued",
                job_id=job_id,
                gap_seconds=int(gap),
            )


async def register_sync_jobs(
    container: AsyncContainer,
    job_scheduler: JobScheduler,
) -> None:
    """Wire container reference + register 5 sync/integrity jobs as text refs.

    Per-job ``misfire_grace_time`` matches each cadence (tight for high-frequency,
    1h for heavy daily). After registration, scans ``job_history`` for missed
    daily/12h runs and enqueues one-off catch-ups.
    """
    set_container(container)

    # UTC wall-clock anchored — bar-aligned crons eliminate phase drift on restart.
    # Strategy correctness depends on bar-close events arriving on time; lag/gaps
    # cause missed entries/exits. See debug-260505-1213-15m-freshness-delay.md.
    #
    # sync_1m runs at +2s from bar close. Gives the data provider time to settle the
    # just-closed bar. Cascade runs in-process after 1m upsert — no extra API calls.
    # coalesce + max_instances=1 are APScheduler defaults — overlap prevention built-in.
    #
    # Per-job grace rationale (overrides global 300s default):
    #   sync_1m            120s  — tight; cascade lookback (100min) heals missed ticks
    #   sync_verify_cascade 600s — 10min slip OK for read-only check
    #   sync_backfill     3600s — 1h recovery for heavy daily 03:00 UTC run
    #   sync_integrity    3600s — same
    #   sync_repair       1800s — 30min slip on bi-daily 12h cron
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_1m",
        job_id="sync_1m",
        cron_expression="*/1 * * * *",
        second=2,
        misfire_grace_time=120,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_verify_cascade",
        job_id="sync_verify_cascade",
        cron_expression="0 * * * *",
        misfire_grace_time=600,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_backfill",
        job_id="sync_backfill",
        hour=3,
        minute=0,
        misfire_grace_time=3600,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_integrity",
        job_id="sync_integrity",
        hour=4,
        minute=0,
        misfire_grace_time=3600,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_repair",
        job_id="sync_repair",
        cron_expression="0 */12 * * *",
        misfire_grace_time=1800,
    )

    # Catch-up sweep: enqueue one-off runs for any daily/12h job whose last
    # success exceeds its per-job max_gap. Must run AFTER cron registration so
    # any catch-up's _catchup suffix lives alongside the real cron schedule.
    history_repo = await container.get(JobHistoryRepository)
    await enqueue_missed_catchups(history_repo, job_scheduler)

    logger.info("market_data.registered_sync_jobs", job_count=5)
