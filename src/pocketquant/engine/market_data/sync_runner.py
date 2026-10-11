"""Scheduled market-data jobs, run for every exchange through its ``SyncPolicy``.

sync_1m polls each policy's tracked symbols via REST and, for cascade policies,
aggregates 1m → 5m/15m/1h/4h/1d in-process (no extra API calls). sync_backfill,
sync_integrity and sync_repair sweep each policy's integrity intervals.
sync_verify_cascade compares REST 5m bars with cascade-computed 5m bars hourly.

All job entrypoints are module-level coroutines so APScheduler can serialize them
as text references for MongoDBJobStore. Dependencies are resolved at execution
time from a module-level container reference set by ``register_sync_jobs``.

``symbol`` is composite ``{code}:{exchange}`` throughout — no separate exchange param.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import (
    SOURCE_REST_BACKFILL,
    SOURCE_REST_REPAIR,
    SOURCE_REST_SYNC_1M,
)
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
from pocketquant.engine.market_data.bar_integrity import (
    DIVERGENCE_ALERT_FRACTION,
    PRICE_THRESHOLD_PCT,
    VOLUME_THRESHOLD_PCT,
    check_integrity,
    repair_integrity,
    verify_one_symbol,
)
from pocketquant.engine.market_data.sync_policy import SyncPolicies, SyncPolicy
from pocketquant.engine.market_data.sync_service import (
    SyncResponse,
    SyncService,
    SyncSymbolCommand,
)

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)

_MODULE = "pocketquant.engine.market_data.sync_runner"

# Catch-up targets — heavy daily/12h jobs that silently drop runs when a restart
# spans their (per-job) misfire_grace_time window. (job_id, func_ref, max_gap_s).
# Excludes sync_1m (cascade lookback heals) and sync_verify_cascade (read-only).
#
# max_gap = expected_interval + per-job grace, e.g. sync_backfill runs every 24h
# with 1h grace → 25h gap means the daily run was definitely missed.
CATCHUP_TARGETS: list[tuple[str, str, int]] = [
    ("sync_backfill", f"{_MODULE}:sync_backfill", 86400 + 3600),  # 24h + 1h
    ("sync_integrity", f"{_MODULE}:sync_integrity", 86400 + 3600),
    ("sync_repair", f"{_MODULE}:sync_repair", 43200 + 1800),  # 12h + 30min
]

# Set once at startup by register_sync_jobs; jobs resolve dependencies through it.
_container: AsyncContainer | None = None

SyncTarget = tuple[str, tuple[Interval, ...], int]
RecordedBody = Callable[[str | None], Awaitable[tuple[int, int] | None]]


def set_container(container: AsyncContainer) -> None:
    global _container
    _container = container


def _get_container() -> AsyncContainer:
    if _container is None:
        raise RuntimeError(
            "sync_runner container not initialized. "
            "Call set_container() before scheduler executes any job."
        )
    return _container


def _ms_since(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


async def _tracked_policies(
    repo: TrackedSymbolRepository, policies: SyncPolicies
) -> list[tuple[str, SyncPolicy]]:
    pairs: list[tuple[str, SyncPolicy]] = []
    for ts in await repo.list_all():
        policy = policies.policy_for(ts.symbol)
        if policy is not None:
            pairs.append((ts.symbol, policy))
    return pairs


async def _run_recorded(name: str, history_repo: JobHistoryRepository, body: RecordedBody) -> None:
    """Own the job_history start/finish/failure records around ``body(doc_id)``."""
    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        totals = await body(doc_id)
        if doc_id and totals is not None:
            await history_repo.record_finish(
                doc_id,
                status="completed",
                duration_ms=_ms_since(started),
                total_inserted=totals[0],
                total_fetched=totals[1],
            )
        elif doc_id:
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


async def _record_detail(
    history_repo: JobHistoryRepository,
    doc_id: str | None,
    job_name: str,
    symbol: str,
    interval: Interval,
    *,
    result: SyncResponse | None = None,
    error: str | None = None,
) -> None:
    if not doc_id:
        return
    try:
        await history_repo.record_detail(
            doc_id,
            symbol=symbol,
            interval=interval.value,
            bars_fetched=result.bars_fetched if result else 0,
            bars_inserted=result.bars_synced if result else 0,
            filtered_existing=result.filtered_existing if result else 0,
            filtered_misaligned=result.filtered_misaligned if result else 0,
            status=result.status if result else "error",
            error=result.message if result else error,
        )
    except Exception:
        logger.warning("job_history.record_detail_failed", job_id=job_name, exc_info=True)


async def _sync_symbols(
    job_name: str,
    targets: list[SyncTarget],
    source: str,
    sync_service: SyncService,
    history_repo: JobHistoryRepository,
    doc_id: str | None,
) -> tuple[int, int]:
    """Sync each (symbol, intervals, n_bars) target; return (total_inserted, total_fetched).

    Every target runs even when one fails; the first error is raised at the end.
    """
    logger.info(f"market_data.{job_name}.started")
    if not targets:
        logger.warning(f"market_data.{job_name}.skipped", reason="no_tracked_symbols")
        return 0, 0

    synced = errors = total_inserted = total_fetched = 0
    first_error: Exception | None = None
    for symbol, intervals, n_bars in targets:
        for interval in intervals:
            try:
                command = SyncSymbolCommand(
                    symbol=symbol, interval=interval, n_bars=n_bars, source=source
                )
                result = await sync_service.sync_one(command)
                total_inserted += result.bars_synced
                total_fetched += result.bars_fetched
                await _record_detail(
                    history_repo, doc_id, job_name, symbol, interval, result=result
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
                await _record_detail(history_repo, doc_id, job_name, symbol, interval, error=str(e))

    logger.info(f"market_data.{job_name}.completed", synced_count=synced, error_count=errors)
    if first_error:
        raise first_error
    return total_inserted, total_fetched


async def _capped(
    policy: SyncPolicy, coro: Coroutine[Any, Any, tuple[int, int]]
) -> tuple[int, int]:
    """Bound one policy's poll so a slow venue cannot hold up the policies after it."""
    if policy.poll_time_cap_s is None:
        return await coro
    try:
        return await asyncio.wait_for(coro, policy.poll_time_cap_s)
    except TimeoutError:
        logger.warning(
            "market_data.sync.poll_time_cap_hit",
            exchange=policy.exchange,
            cap_s=policy.poll_time_cap_s,
        )
        return 0, 0


# APScheduler entrypoints — referenced by text as f"{_MODULE}:<funcname>".
async def sync_1m() -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    sync_service = await container.get(SyncService)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    policies = await container.get(SyncPolicies)

    async def body(doc_id: str | None) -> tuple[int, int]:
        now = datetime.now(UTC)
        tracked = await _tracked_policies(tracked_symbol_repo, policies)
        total_inserted = total_fetched = 0
        for policy in policies:
            symbols = [s for s, p in tracked if p is policy]
            targets = [
                (s, policy.poll_intervals, policy.poll_n_bars)
                for s in symbols
                if policies.market_calendar(s).is_open(now)
            ]
            inserted, fetched = await _capped(
                policy,
                _sync_symbols(
                    "sync_1m", targets, SOURCE_REST_SYNC_1M, sync_service, history_repo, doc_id
                ),
            )
            total_inserted += inserted
            total_fetched += fetched
            if policy.cascade:
                await _cascade(symbols, policy.cascade_lookback_minutes, bar_repo)
        return total_inserted, total_fetched

    await _run_recorded("sync_1m", history_repo, body)


async def _cascade(symbols: list[str], lookback_minutes: int, bar_repo: BarRepository) -> None:
    cascade_total: dict[Interval, int] = {}
    for symbol in symbols:
        try:
            counts = await cascade_for_symbol(
                symbol, lookback_minutes=lookback_minutes, bar_repo=bar_repo
            )
            for tf, count in counts.items():
                cascade_total[tf] = cascade_total.get(tf, 0) + count
        except Exception:
            logger.error("sync_1m.cascade_failed", symbol=symbol, exc_info=True)
    logger.info(
        "sync_1m.cascade_summary",
        cascade_counts={tf.value: n for tf, n in cascade_total.items()},
    )


async def sync_verify_cascade() -> None:
    """Hourly sanity check of every cascade policy's symbols: REST 5m vs cascade 5m.

    O/H/L/C are compared against PRICE_THRESHOLD_PCT and V against VOLUME_THRESHOLD_PCT;
    a symbol alerts when divergence_count/compared > DIVERGENCE_ALERT_FRACTION.
    """
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    policies = await container.get(SyncPolicies)

    async def body(doc_id: str | None) -> None:
        tracked = [
            (s, p) for s, p in await _tracked_policies(tracked_symbol_repo, policies) if p.cascade
        ]
        if not tracked:
            logger.warning("sync_verify_cascade.skipped", reason="no_tracked_symbols")
            return
        logger.info("sync_verify_cascade.started", symbols=len(tracked))
        for s, policy in tracked:
            symbol = s.upper()
            try:
                summary = await verify_one_symbol(
                    symbol, provider=policy.data_provider, bar_repo=bar_repo
                )
            except Exception as exc:
                logger.error("sync_verify_cascade.symbol_failed", symbol=symbol, error=str(exc))
                continue
            _log_verify_summary(symbol, summary)

    await _run_recorded("sync_verify_cascade", history_repo, body)


def _log_verify_summary(symbol: str, summary: dict) -> None:
    if summary.get("rest_empty"):
        logger.warning("sync_verify_cascade.rest_empty", symbol=symbol)
        return
    if summary.get("cascade_empty"):
        logger.warning(
            "sync_verify_cascade.cascade_empty",
            symbol=symbol,
            reason="no_cascade_5m_bars_in_window",
        )
        return
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


async def sync_backfill() -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    sync_service = await container.get(SyncService)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    policies = await container.get(SyncPolicies)

    async def body(doc_id: str | None) -> tuple[int, int]:
        targets = [
            (s, p.integrity_intervals, p.backfill_n_bars)
            for s, p in await _tracked_policies(tracked_symbol_repo, policies)
        ]
        return await _sync_symbols(
            "sync_backfill", targets, SOURCE_REST_BACKFILL, sync_service, history_repo, doc_id
        )

    await _run_recorded("sync_backfill", history_repo, body)


async def sync_integrity() -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    policies = await container.get(SyncPolicies)

    async def body(doc_id: str | None) -> None:
        for symbol, policy in await _tracked_policies(tracked_symbol_repo, policies):
            for interval in policy.integrity_intervals:
                report = await check_integrity(
                    symbol, interval, bar_repo, calendar=policies.market_calendar(symbol)
                )
                if report["misaligned_count"] or report["missing_count"]:
                    logger.warning(
                        "integrity.issues_found",
                        symbol=symbol,
                        interval=interval.value,
                        misaligned=report["misaligned_count"],
                        missing=report["missing_count"],
                    )

    await _run_recorded("sync_integrity", history_repo, body)


async def sync_repair() -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    sync_service = await container.get(SyncService)
    tracked_symbol_repo = await container.get(TrackedSymbolRepository)
    bar_repo = await container.get(BarRepository)
    policies = await container.get(SyncPolicies)

    async def body(doc_id: str | None) -> None:
        for symbol, policy in await _tracked_policies(tracked_symbol_repo, policies):
            for interval in policy.integrity_intervals:
                result = await repair_integrity(
                    symbol,
                    interval,
                    bar_repo,
                    sync_service,
                    source=SOURCE_REST_REPAIR,
                    calendar=policies.market_calendar(symbol),
                )
                if result["deleted"] or result["gaps_resynced"]:
                    logger.info(
                        "integrity.repaired",
                        symbol=symbol,
                        interval=interval.value,
                        deleted=result["deleted"],
                        gaps_resynced=result["gaps_resynced"],
                    )

    await _run_recorded("sync_repair", history_repo, body)


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
    ``<job_id>_catchup``, but the wrapper inside (``_run_recorded``) writes a
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
    """Wire the container, register the 5 sync/integrity jobs as text refs, enqueue catch-ups."""
    set_container(container)

    # Bar-aligned UTC crons avoid phase drift on restart; strategies need bar-close events
    # on time (see debug-260505-1213-15m-freshness-delay.md). sync_1m fires +2s after bar
    # close so the provider settles the just-closed bar. coalesce + max_instances=1 are
    # APScheduler defaults. Per-job grace overrides the global 300s: sync_1m 120s (cascade
    # lookback heals missed ticks), sync_verify_cascade 600s (read-only), sync_backfill and
    # sync_integrity 3600s (heavy daily runs), sync_repair 1800s (12h cron).
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
