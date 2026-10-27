"""Background sync jobs for market data — single 1m REST fetch + cascade aggregation.

sync_1m runs every minute: fetches last 100 1m bars per tracked symbol via REST,
upserts to MongoDB, then cascade-aggregates 1m → 5m/15m/1h/4h/1d (math, no extra
API calls). Sole MongoDB writer for `bars` collection across all timeframes.

sync_verify_cascade runs hourly: for every tracked symbol it fetches REST 5m
bars, compares them with the cascade-computed 5m, and logs divergence alerts.

data_lag_check runs every minute after sync_1m: measures how far each tracked
symbol's 1m feed runs behind real time and stores the reading in Redis for the
UI. It logs only when a symbol's feed state changes.

All job entrypoints are module-level coroutines so APScheduler can serialize them
as text references for MongoDBJobStore. Dependencies (SyncService, repos) are
resolved at job-execution time from a module-level container reference set by
`register_sync_jobs`.

``symbol`` is composite ``{code}:{exchange}`` throughout — no separate exchange param.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pocketquant.core.common.constants import CACHE_KEY_DATA_LAG, TTL_DATA_LAG
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import (
    SOURCE_REST_BACKFILL,
    SOURCE_REST_REPAIR,
    SOURCE_REST_SYNC_1M,
)
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
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
from pocketquant.engine.market_data.data_lag_service import FeedState, compute_data_lag
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)

# All timeframes synced / integrity-checked: 1m via REST, 5m–1d via cascade,
# 1w via REST (Binance serves Monday-aligned weekly klines natively — cascading
# from 1m would mis-bucket since floor-of-epoch aligns weeks to Thursday).
#
# For a calendar-based asset class both 1d and 1w are REST-only: their sessions
# open the evening before, so a cascade bucketed across UTC midnight would
# produce a daily bar that never matches the vendor chart. The list below is
# unchanged because REST already fetches both for every symbol; what differs is
# that ``cascade_tfs`` stops deriving 1d for those calendars.
SYNC_INTERVALS = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
    Interval.WEEK_1,
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


async def _tracked(name: str, body: Callable[[str | None], Awaitable[dict | None]]) -> None:
    """Run one job body and write its job_history document.

    A failed body is recorded here and logged, not re-raised: the scheduler's
    error hook would record the same run a second time. Only when the start
    record itself failed does the error reach the scheduler, which records it.
    A failed history write is logged and never fails the job.
    """
    history_repo = await _get_container().get(JobHistoryRepository)
    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    totals: dict = {}
    error: str | None = None
    try:
        totals = await body(doc_id) or {}
    except Exception as exc:
        if doc_id is None:
            raise
        logger.error(f"market_data.{name}.failed", exc_info=True)
        error = str(exc)
    if doc_id is None:
        return
    try:
        await history_repo.record_finish(
            doc_id,
            status="failed" if error else "completed",
            duration_ms=_ms_since(started),
            error=error,
            **totals,
        )
    except Exception:
        logger.warning("job_history.record_finish_failed", job_id=name, exc_info=True)


async def _sync_by_intervals(
    intervals: list[Interval],
    n_bars: int,
    job_name: str,
    sync_service: SyncService,
    tracked_symbol_repo: TrackedSymbolRepository,
    history_repo: JobHistoryRepository,
    doc_id: str | None,
    source: str,
    calendar_factory: TradingCalendarFactory,
) -> dict:
    """For each tracked symbol, sync the given intervals via REST provider.

    Returns ``total_inserted`` and ``total_fetched`` across all sub-syncs. Every
    symbol is tried; the first error is raised at the end.

    A symbol whose market is shut is skipped without calling the provider: there
    is nothing to fetch, and asking anyway spends rate limit on an empty answer.
    """
    logger.debug(f"market_data.{job_name}.started")

    async def detail(**fields: Any) -> None:
        if not doc_id:
            return
        try:
            await history_repo.record_detail(doc_id, **fields)
        except Exception:
            logger.warning("job_history.record_detail_failed", job_id=job_name, exc_info=True)

    symbols = [ts.symbol for ts in await tracked_symbol_repo.list_all()]
    totals = {"total_inserted": 0, "total_fetched": 0}
    if not symbols:
        logger.warning(f"market_data.{job_name}.skipped", reason="no_tracked_symbols")
        return totals

    synced = errors = skipped = 0
    first_error: Exception | None = None
    # One interval of grace after the close, so the session's final bar is still
    # fetched once it has actually closed.
    grace = timedelta(seconds=INTERVAL_SECONDS[max(intervals, key=lambda i: INTERVAL_SECONDS[i])])

    for symbol in symbols:
        calendar = await calendar_factory.for_symbol(symbol)
        now = datetime.now(UTC)
        if not (calendar.is_open(now) or (now - calendar.previous_close(now)) <= grace):
            skipped += 1
            logger.debug(
                f"market_data.{job_name}.symbol_skipped_closed",
                symbol=symbol,
                calendar_id=calendar.calendar_id,
            )
            await detail(
                symbol=symbol,
                interval=intervals[0].value,
                bars_fetched=0,
                bars_inserted=0,
                filtered_existing=0,
                filtered_misaligned=0,
                status="skipped",
                error="closed",
            )
            continue

        for interval in intervals:
            command = SyncSymbolCommand(
                symbol=symbol, interval=interval, n_bars=n_bars, source=source
            )
            try:
                result = await sync_service.sync_one(command)
            except Exception as e:
                logger.error(
                    f"market_data.{job_name}.symbol_failed",
                    symbol=symbol,
                    interval=interval.value,
                    error=str(e),
                )
                errors += 1
                first_error = first_error or e
                await detail(
                    symbol=symbol,
                    interval=interval.value,
                    bars_fetched=0,
                    bars_inserted=0,
                    filtered_existing=0,
                    filtered_misaligned=0,
                    status="error",
                    error=str(e),
                )
                continue
            totals["total_inserted"] += result.bars_synced
            totals["total_fetched"] += result.bars_fetched
            await detail(
                symbol=symbol,
                interval=interval.value,
                bars_fetched=result.bars_fetched,
                bars_inserted=result.bars_synced,
                filtered_existing=result.filtered_existing,
                filtered_misaligned=result.filtered_misaligned,
                status=result.status,
                error=result.message,
            )
            if result.status == "completed":
                synced += 1
            else:
                errors += 1

    logger.debug(
        f"market_data.{job_name}.completed",
        synced_count=synced,
        error_count=errors,
        skipped_count=skipped,
    )
    if first_error:
        raise first_error
    return totals


async def _rest_sync(
    name: str, intervals: list[Interval], n_bars: int, source: str, doc_id: str | None
) -> dict:
    container = _get_container()
    return await _sync_by_intervals(
        intervals,
        n_bars,
        name,
        await container.get(SyncService),
        await container.get(TrackedSymbolRepository),
        await container.get(JobHistoryRepository),
        doc_id,
        source=source,
        calendar_factory=await container.get(TradingCalendarFactory),
    )


# APScheduler entrypoints — referenced by text as
# "pocketquant.engine.market_data.app_services.sync_jobs:<funcname>"
async def sync_1m() -> None:
    """Fetch the last 100 1m bars per symbol, then cascade them to 5m-1d.

    The cascade runs even when a REST fetch failed: the symbols that did sync
    still need their higher timeframes. The failure is recorded afterwards.
    """
    container = _get_container()
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    calendar_factory = await container.get(TradingCalendarFactory)

    async def body(doc_id: str | None) -> dict:
        try:
            return await _rest_sync(
                "sync_1m", [Interval.MINUTE_1], 100, SOURCE_REST_SYNC_1M, doc_id
            )
        finally:
            cascade_total: dict[Interval, int] = {}
            for ts in await tracked_symbol_repo.list_all():
                try:
                    counts = await cascade_for_symbol(
                        ts.symbol,
                        lookback_minutes=100,
                        bar_repo=bar_repo,
                        calendar=await calendar_factory.for_symbol(ts.symbol),
                    )
                except Exception:
                    logger.error("sync_1m.cascade_failed", symbol=ts.symbol, exc_info=True)
                    continue
                for tf, count in counts.items():
                    cascade_total[tf] = cascade_total.get(tf, 0) + count
            logger.debug(
                "sync_1m.cascade_summary",
                cascade_counts={tf.value: n for tf, n in cascade_total.items()},
            )

    await _tracked("sync_1m", body)


async def sync_backfill() -> None:
    await _tracked(
        "sync_backfill",
        lambda doc_id: _rest_sync(
            "sync_backfill", SYNC_INTERVALS, 5000, SOURCE_REST_BACKFILL, doc_id
        ),
    )


async def sync_integrity() -> None:
    """Log misaligned, missing and unexpected bars per symbol and timeframe.

    Each symbol is checked on its own; the run fails once all are done if any failed.
    """
    container = _get_container()
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    calendar_factory = await container.get(TradingCalendarFactory)

    async def body(_: str | None) -> None:
        tracked = await tracked_symbol_repo.list_all()
        failed = 0
        for ts in tracked:
            try:
                calendar = await calendar_factory.for_symbol(ts.symbol)
                for interval in SYNC_INTERVALS:
                    report = await check_integrity(ts.symbol, interval, bar_repo, calendar)
                    if (
                        report["misaligned_count"]
                        or report["missing_count"]
                        or report.get("unexpected_count")
                    ):
                        logger.warning(
                            "integrity.issues_found",
                            symbol=ts.symbol,
                            interval=interval.value,
                            misaligned=report["misaligned_count"],
                            missing=report["missing_count"],
                            unexpected=report.get("unexpected_count", 0),
                            unexpected_ranges=report.get("unexpected_ranges", [])[:5],
                        )
            except Exception:
                failed += 1
                logger.error("integrity.symbol_failed", symbol=ts.symbol, exc_info=True)
        if failed:
            raise RuntimeError(f"{failed} of {len(tracked)} symbols failed")

    await _tracked("sync_integrity", body)


async def sync_repair() -> None:
    """Delete misaligned bars and re-sync gaps per symbol and timeframe.

    Each symbol is repaired on its own; the run fails once all are done if any failed.
    """
    container = _get_container()
    sync_service = await container.get(SyncService)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    calendar_factory = await container.get(TradingCalendarFactory)

    async def body(_: str | None) -> None:
        tracked = await tracked_symbol_repo.list_all()
        failed = 0
        for ts in tracked:
            try:
                calendar = await calendar_factory.for_symbol(ts.symbol)
                for interval in SYNC_INTERVALS:
                    result = await repair_integrity(
                        ts.symbol,
                        interval,
                        bar_repo,
                        sync_service,
                        calendar,
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
            except Exception:
                failed += 1
                logger.error("integrity.repair_failed", symbol=ts.symbol, exc_info=True)
        if failed:
            raise RuntimeError(f"{failed} of {len(tracked)} symbols failed")

    await _tracked("sync_repair", body)


async def _verify_one_symbol(
    symbol: str,
    *,
    provider: IDataProviderPort,
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

    rest_by_dt = {b.datetime: b for b in rest_bars if b.datetime}
    cascade_by_dt = {b.datetime: b for b in cascade_bars if b.datetime}
    # This job runs seconds before sync_1m stores the newest 1m bar, so the newest
    # stored bucket can still be one minute short. Stored 1m bars arrive in order,
    # so only that bucket can be; it is left out.
    compared_dts = sorted(rest_by_dt.keys() & cascade_by_dt.keys())[:-1]

    compared = 0
    divergence_count = 0
    samples: list[dict] = []
    for bar_dt in compared_dts:
        compared += 1
        fields_diff = compare_bar_fields(rest_by_dt[bar_dt], cascade_by_dt[bar_dt])
        if any(fields_diff.values()):
            divergence_count += 1
            if len(samples) < 3:
                samples.append({"datetime": bar_dt.isoformat(), "fields": fields_diff})

    return {
        "symbol": symbol,
        "compared": compared,
        "divergence_count": divergence_count,
        "samples": samples,
    }


async def sync_verify_cascade() -> None:
    """Hourly full-fleet sanity check: REST 5m vs cascade 5m, full OHLCV per field.

    Iterates every tracked symbol. Each comparison checks O/H/L/C against
    PRICE_THRESHOLD_PCT and V against VOLUME_THRESHOLD_PCT. Alerts when
    divergence_count/compared > DIVERGENCE_ALERT_FRACTION for that symbol.
    """
    container = _get_container()
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    provider = await container.get(IDataProviderPort)

    async def body(_: str | None) -> None:
        tracked = await tracked_symbol_repo.list_all()
        if not tracked:
            logger.warning("sync_verify_cascade.skipped", reason="no_tracked_symbols")
            return

        logger.info("sync_verify_cascade.started", symbols=len(tracked))

        for ts in tracked:
            symbol = ts.symbol.upper()
            try:
                summary = await _verify_one_symbol(symbol, provider=provider, bar_repo=bar_repo)
            except Exception as exc:
                logger.error("sync_verify_cascade.symbol_failed", symbol=symbol, error=str(exc))
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
                logger.debug(
                    "sync_verify_cascade.ok",
                    symbol=symbol,
                    compared=compared,
                    divergence_count=div,
                )

    await _tracked("sync_verify_cascade", body)


def _log_feed_transition(
    previous: dict | None, state: FeedState, symbol: str, lag_seconds: int | None
) -> None:
    """Log a feed state change once, never the steady state.

    A delayed feed stays delayed all session, so logging every reading would be
    a per-symbol-per-minute line. Entering STUCK is the one actionable change and
    is a WARNING; the rest (a session opening delayed, a feed recovering) are
    bounded to a few per symbol per day and stay INFO.
    """
    before = previous.get("state") if previous else FeedState.UNKNOWN.value
    if before == state.value:
        return
    emit = logger.warning if state is FeedState.STUCK else logger.info
    emit(
        "data_lag.state_changed",
        symbol=symbol,
        from_state=before,
        to_state=state.value,
        lag_seconds=lag_seconds,
    )


async def data_lag_check() -> None:
    container = _get_container()
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    sync_status_repo = await container.get(SyncStatusRepository)
    calendar_factory = await container.get(TradingCalendarFactory)
    cache = await container.get(Cache)

    async def body(_: str | None) -> None:
        now = datetime.now(UTC)
        for ts in await tracked_symbol_repo.list_all():
            symbol = ts.symbol.upper()
            try:
                calendar = await calendar_factory.for_symbol(symbol)
                snapshot = await compute_data_lag(
                    symbol, bar_repo, sync_status_repo, calendar, now=now
                )
                key = CACHE_KEY_DATA_LAG.format(symbol=symbol)
                previous = await cache.get(key)
                await cache.set(key, snapshot.to_cache_dict(), ttl=TTL_DATA_LAG)
            except Exception:
                logger.error("data_lag.check_failed", symbol=symbol, exc_info=True)
                continue
            _log_feed_transition(previous, snapshot.state, symbol, snapshot.lag_seconds)

    await _tracked("data_lag_check", body)


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
    ``<job_id>_catchup``, but the wrapper inside (``_tracked``) writes a
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
    """Register 6 sync/integrity/lag jobs as text refs.

    The container reference is set at app startup (``set_container``), before
    any job can run; ``container`` is used here only for the catch-up sweep.

    Per-job ``misfire_grace_time`` matches each cadence (tight for high-frequency,
    1h for heavy daily). After registration, scans ``job_history`` for missed
    daily/12h runs and enqueues one-off catch-ups.
    """
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
    # data_lag_check reads what sync_1m just wrote, so it runs mid-minute.
    # A tight grace: a reading older than a minute is replaced by the next one.
    job_scheduler.add_cron_job(
        f"{_MODULE}:data_lag_check",
        job_id="data_lag_check",
        cron_expression="*/1 * * * *",
        second=30,
        misfire_grace_time=60,
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

    # Every registered trigger must be UTC. One that picked up the host zone
    # would fire at a different instant per machine and pickle that zone into
    # the shared Mongo jobstore, where it outlives the process that wrote it.
    for job in job_scheduler.get_raw_jobs():
        trigger_tz = getattr(job.trigger, "timezone", None)
        if trigger_tz is not None and str(trigger_tz) != "UTC":
            raise RuntimeError(
                f"Job {job.id!r} registered with a non-UTC trigger timezone "
                f"{str(trigger_tz)!r}; cron triggers must pass timezone=UTC."
            )

    # Catch-up sweep: enqueue one-off runs for any daily/12h job whose last
    # success exceeds its per-job max_gap. Must run AFTER cron registration so
    # any catch-up's _catchup suffix lives alongside the real cron schedule.
    history_repo = await container.get(JobHistoryRepository)
    await enqueue_missed_catchups(history_repo, job_scheduler)

    logger.info("market_data.registered_sync_jobs", job_count=6)
