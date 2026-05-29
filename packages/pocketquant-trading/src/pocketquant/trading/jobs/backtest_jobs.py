"""Async job worker for subscription-scoped backtest runs.

Each subscription maps to a single cached backtest result (keyed by sub_id).
Jobs are enqueued via JobScheduler.add_one_off_job() and reference this module
as a text path so APScheduler can serialize them in MongoDBJobStore.

NOTE: The strategy must already be loaded in StrategyAppService._configs before
this job executes. If the app restarts and wipes in-memory state, the job fails
with a clear 'strategy config not in memory' error. Subscribe via
POST /strategies/{strategy_code}/subscriptions before running backtest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pocketquant.core.common.logging import get_logger

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level container reference — set once at startup via set_container().
# Job functions resolve their dependencies via this reference at execution time.
# ---------------------------------------------------------------------------

_container: AsyncContainer | None = None


def set_container(container: AsyncContainer) -> None:
    global _container
    _container = container


def _get_container() -> AsyncContainer:
    if _container is None:
        raise RuntimeError(
            "backtest_jobs container not initialized. "
            "Call set_container() before any backtest job executes."
        )
    return _container


# ---------------------------------------------------------------------------
# Job entrypoint — top-level coroutine referenced by APScheduler as text path:
#   "pocketquant.trading.jobs.backtest_jobs:run_subscription_backtest"
# ---------------------------------------------------------------------------


async def run_subscription_backtest(subscription_id: str) -> None:
    """Execute and cache a backtest for a single subscription.

    Steps:
      1. Resolve deps from DI container.
      2. Load subscription — bail if deleted mid-flight.
      3. Mark status='running'.
      4. Build BacktestConfig from in-memory strategy config + subscription overrides.
      5. Load strategy under a synthetic_id scoped to this job (C2 concurrency fix).
      6. Run BacktestAppService (persist_results=False).
      7. M1 TOCTOU: re-check subscription exists before writing result.
      8. save_for_subscription honors result.status (C1 fix — 'completed' or 'failed').
      9. On exception: M1 re-check before upsert_status('failed') + re-raise.
     10. Finally: unload synthetic_id only — user's live strategy is untouched.
    """
    from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
    from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
    from pocketquant.core.common.messaging import EventBus
    from pocketquant.core.persistence.repositories.bar_repository import BarRepository
    from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
    from pocketquant.trading.jobs.backtest_strategy_loader import (
        build_backtest_config,
        load_strategy_for_backtest,
        resolve_date_range,
    )
    from pocketquant.trading.persistence.subscription_repository import (
        SubscriptionRepository,
    )

    container = _get_container()
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    bt_repo: BacktestRepository = await container.get(BacktestRepository)
    bar_repo: BarRepository = await container.get(BarRepository)
    event_bus: EventBus = await container.get(EventBus)
    strategy_app_service: StrategyAppService = await container.get(StrategyAppService)

    # 1. Bail silently if subscription was deleted before the job ran
    sub = await sub_repo.get(subscription_id)
    if sub is None:
        logger.warning("backtest_jobs.subscription_not_found", sub_id=subscription_id)
        return

    strategy_code = sub.strategy_code
    symbol = sub.symbol  # composite "{code}:{exchange}"
    interval = sub.interval.value  # string e.g. "1h"

    await bt_repo.upsert_status(subscription_id, strategy_code=strategy_code, status="running")

    # synthetic_id is set inside the try block; track it for finally cleanup
    synthetic_id: str | None = None

    try:
        # 2. Validate strategy config is in memory
        base_config = strategy_app_service._configs.get(strategy_code)  # pyright: ignore[reportPrivateUsage]
        if base_config is None:
            raise ValueError(
                f"Strategy config for '{strategy_code}' not in memory. "
                "Subscribe to the strategy via "
                "POST /strategies/{strategy_code}/subscriptions before running backtest."
            )

        start_date, end_date = await resolve_date_range(bar_repo, symbol, interval)
        config = build_backtest_config(
            base_config, strategy_code, symbol, interval, start_date, end_date
        )

        # C2: load under a synthetic_id unique to this sub — no concurrent job clobber
        broker, synthetic_id = await load_strategy_for_backtest(
            strategy_app_service,
            base_config,
            strategy_code,
            subscription_id,
            symbol,
            interval,
            event_bus=event_bus,
        )

        runner = BacktestAppService(
            event_bus=event_bus,
            broker=broker,
            backtest_repository=bt_repo,
            bar_repository=bar_repo,
            persist_results=False,
        )
        result = await runner.run(config)

        # M1 TOCTOU: subscription may have been deleted while the run was in progress
        if await sub_repo.get(subscription_id) is None:
            logger.warning(
                "backtest_jobs.subscription_deleted_during_run",
                sub_id=subscription_id,
                strategy_code=strategy_code,
            )
            return

        # C1: save_for_subscription maps result.status → 'completed' or 'failed'
        await bt_repo.save_for_subscription(subscription_id, result)

        logger.info(
            "backtest_jobs.completed",
            sub_id=subscription_id,
            strategy_code=strategy_code,
            symbol=symbol,  # composite
            interval=interval,
            result_status=result.status,
        )

    except Exception as exc:
        logger.error(
            "backtest_jobs.failed",
            sub_id=subscription_id,
            strategy_code=strategy_code,
            error=str(exc),
            exc_info=True,
        )
        # M1 TOCTOU: skip writing if sub was deleted while we were running
        if await sub_repo.get(subscription_id) is not None:
            await bt_repo.upsert_status(
                subscription_id,
                strategy_code=strategy_code,
                status="failed",
                error_msg=str(exc)[:500],
            )
        else:
            logger.warning(
                "backtest_jobs.subscription_deleted_during_run",
                sub_id=subscription_id,
                strategy_code=strategy_code,
            )
        raise

    finally:
        # C2: unload the synthetic entry only — user's base strategy_code is untouched
        if synthetic_id is not None:
            try:
                await strategy_app_service.unload_strategy(synthetic_id)
            except Exception as cleanup_exc:
                logger.warning(
                    "backtest_jobs.cleanup_failed",
                    sub_id=subscription_id,
                    synthetic_id=synthetic_id,
                    error=str(cleanup_exc),
                )
