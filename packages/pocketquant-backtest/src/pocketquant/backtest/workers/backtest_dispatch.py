"""Backtest dispatch — shared single + subscription execution paths.

Both the queue worker and (historically) the request handlers need the same
engine-setup-and-run logic. Centralizing it here keeps the synthetic-id
isolation, TOCTOU re-checks, and PaperBroker wiring in one place so the two
dispatch kinds can never drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.jobs.backtest_strategy_loader import (
    build_backtest_config,
    load_strategy_for_backtest,
    resolve_date_range,
)
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.core.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


@dataclass
class BacktestDispatchDeps:
    """Injected dependencies for a dispatch call — resolved once per worker tick."""

    event_bus: EventBus
    bar_repo: BarRepository
    backtest_repo: BacktestRepository
    order_repo: BacktestOrderRepository
    trade_repo: BacktestTradeRepository
    strategy_app_service: StrategyAppService
    subscription_repo: SubscriptionRepository


def _config_from_dict(payload: dict[str, Any]) -> BacktestConfig:
    """Rebuild a BacktestConfig from the serialized request payload."""
    return BacktestConfig(
        strategy_code=payload["strategy_code"],
        symbol=payload["symbol"],
        interval=payload["interval"],
        start_date=date.fromisoformat(payload["start_date"]),
        end_date=date.fromisoformat(payload["end_date"]),
        initial_capital=payload.get("initial_capital", 10_000.0),
        slippage_bps=payload.get("slippage_bps", 10.0),
        commission_bps=payload.get("commission_bps", 10.0),
        parameters=payload.get("parameters") or {},
    )


def config_to_dict(cmd: dict[str, Any]) -> dict[str, Any]:
    """Normalize a RunBacktestCommand-shaped dict into a storable config payload.

    Dates are ISO strings so the doc round-trips through Mongo/JSON unchanged.
    """
    return {
        "strategy_code": cmd["strategy_id"],
        "symbol": cmd["symbol"],
        "interval": cmd["interval"],
        "start_date": cmd["start_date"],
        "end_date": cmd["end_date"],
        "initial_capital": cmd.get("initial_capital", 10_000.0),
        "slippage_bps": cmd.get("slippage_bps", 10.0),
        "commission_bps": cmd.get("commission_bps", 10.0),
        "parameters": cmd.get("parameters") or {},
    }


async def run_single(deps: BacktestDispatchDeps, config_payload: dict[str, Any]) -> BacktestResult:
    """Execute one ad-hoc backtest and persist results to backtest_* collections.

    Mirrors the former synchronous RunBacktestHandler: a fresh PaperBroker wired
    to the event bus (so SL/TP auto-fill on BarCompletedEvent), the strategy
    injected under its own id, run, then unloaded in finally so it never lingers.
    """
    config = _config_from_dict(config_payload)

    strategy_class = STRATEGY_REGISTRY.get(config.strategy_code)
    if strategy_class is None:
        raise ValueError(
            f"Unknown strategy: '{config.strategy_code}'. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}"
        )

    strategy_cfg = StrategyConfig(
        id=config.strategy_code,
        name=config.strategy_code,
        symbol=config.symbol,
        interval=config.interval,
        trigger="bar",
        broker="paper",
        parameters={**config.parameters},
    )

    broker = PaperBroker(
        initial_balance=config.initial_capital,
        slippage_percent=config.slippage_percent,
        event_bus=deps.event_bus,
    )

    strategy_instance = strategy_class(strategy_cfg)
    sid = strategy_instance.id
    if deps.strategy_app_service.get_strategy(sid) is not None:
        await deps.strategy_app_service.unload_strategy(sid)
    await deps.strategy_app_service.inject_prepared_strategy(
        sid, strategy_instance, broker, strategy_instance.config
    )

    try:
        runner = BacktestAppService(
            event_bus=deps.event_bus,
            broker=broker,
            backtest_repository=deps.backtest_repo,
            bar_repository=deps.bar_repo,
            order_repository=deps.order_repo,
            trade_repository=deps.trade_repo,
        )
        return await runner.run(config)
    finally:
        await deps.strategy_app_service.unload_strategy(sid)


async def run_subscription(deps: BacktestDispatchDeps, sub_id: str) -> None:
    """Execute and cache a backtest for one subscription, keyed by sub_id.

    Writes the full result to ``backtest_runs`` under ``sub_id`` (persist via
    BacktestRepository.save_for_subscription), mirroring the per-subscription
    cache that FE polls at ``/subscriptions/{id}/backtest``.

    Preserves the prior job's safety properties:
      - synthetic_id scoped per subscription so concurrent runs never clobber;
      - TOCTOU re-check before writing results (subscription may be deleted
        mid-run);
      - synthetic instance unloaded in finally — the user's live strategy is
        untouched.
    """
    sub = await deps.subscription_repo.get(sub_id)
    if sub is None:
        logger.warning("backtest_dispatch.subscription_not_found", sub_id=sub_id)
        return

    strategy_code = sub.strategy_code
    symbol = sub.symbol  # composite "{code}:{exchange}"
    interval = sub.interval.value

    await deps.backtest_repo.upsert_status(sub_id, strategy_code=strategy_code, status="running")

    synthetic_id: str | None = None
    try:
        base_config = deps.strategy_app_service.get_config(strategy_code)
        if base_config is None:
            raise ValueError(
                f"Strategy config for '{strategy_code}' not in memory. "
                "Subscribe to the strategy before running backtest."
            )

        start_date, end_date = await resolve_date_range(deps.bar_repo, symbol, interval)
        config = build_backtest_config(
            base_config, strategy_code, symbol, interval, start_date, end_date
        )

        broker, synthetic_id = await load_strategy_for_backtest(
            deps.strategy_app_service,
            base_config,
            strategy_code,
            sub_id,
            symbol,
            interval,
            event_bus=deps.event_bus,
        )

        runner = BacktestAppService(
            event_bus=deps.event_bus,
            broker=broker,
            backtest_repository=deps.backtest_repo,
            bar_repository=deps.bar_repo,
            persist_results=False,
        )
        result = await runner.run(config)

        if await deps.subscription_repo.get(sub_id) is None:
            logger.warning(
                "backtest_dispatch.subscription_deleted_during_run",
                sub_id=sub_id,
                strategy_code=strategy_code,
            )
            return

        await deps.backtest_repo.save_for_subscription(sub_id, result)
        logger.info(
            "backtest_dispatch.subscription_completed",
            sub_id=sub_id,
            strategy_code=strategy_code,
            result_status=result.status,
        )

    except Exception as exc:
        logger.error(
            "backtest_dispatch.subscription_failed",
            sub_id=sub_id,
            strategy_code=strategy_code,
            error=str(exc),
            exc_info=True,
        )
        if await deps.subscription_repo.get(sub_id) is not None:
            await deps.backtest_repo.upsert_status(
                sub_id,
                strategy_code=strategy_code,
                status="failed",
                error_msg=str(exc)[:500],
            )
        raise

    finally:
        if synthetic_id is not None:
            try:
                await deps.strategy_app_service.unload_strategy(synthetic_id)
            except Exception as cleanup_exc:
                logger.warning(
                    "backtest_dispatch.cleanup_failed",
                    sub_id=sub_id,
                    synthetic_id=synthetic_id,
                    error=str(cleanup_exc),
                )
