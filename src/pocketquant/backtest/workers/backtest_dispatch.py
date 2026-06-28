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
from pocketquant.backtest.engine.backtest_engine_sandbox import (
    BacktestSandbox,
    build_backtest_sandbox,
)
from pocketquant.backtest.jobs.backtest_strategy_loader import (
    build_backtest_config,
    inject_strategy_into_sandbox,
    resolve_date_range,
)
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
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
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


@dataclass
class BacktestDispatchDeps:
    bar_repo: BarRepository
    backtest_repo: BacktestRepository
    order_repo: BacktestOrderRepository
    trade_repo: BacktestTradeRepository
    # Live engine — read-only here, for the user's per-subscription StrategyConfig
    # (parameters) lookup. Backtests run in their own sandbox, never on this engine.
    strategy_app_service: StrategyAppService
    subscription_repo: SubscriptionRepository


def _config_from_dict(payload: dict[str, Any]) -> BacktestConfig:
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

    Runs in an isolated sandbox (own EventBus + StrategyAppService) so replayed
    bars and synthetic exit fills never reach the live execution engine, and the
    strategy is injected under its own id then torn down with the sandbox.
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

    sandbox = await build_backtest_sandbox()
    try:
        broker = sandbox.create_broker(
            initial_balance=config.initial_capital,
            slippage_percent=config.slippage_percent,
        )
        strategy_instance = strategy_class(strategy_cfg)
        await sandbox.strategy_app_service.inject_prepared_strategy(
            strategy_instance.id, strategy_instance, broker, strategy_instance.config
        )

        runner = BacktestAppService(
            event_bus=sandbox.event_bus,
            broker=broker,
            backtest_repository=deps.backtest_repo,
            bar_repository=deps.bar_repo,
            order_repository=deps.order_repo,
            trade_repository=deps.trade_repo,
        )
        return await runner.run(config)
    finally:
        await sandbox.aclose()


async def run_subscription(deps: BacktestDispatchDeps, sub_id: str) -> None:
    """Execute and cache a backtest for one subscription, keyed by sub_id.

    Writes the full result to ``backtest_runs`` under ``sub_id`` (persist via
    BacktestRepository.save_for_subscription), mirroring the per-subscription
    cache that FE polls at ``/subscriptions/{id}/backtest``.

    Preserves the prior job's safety properties:
      - synthetic_id scoped per subscription so the user's live strategy is
        untouched;
      - TOCTOU re-check before writing results (subscription may be deleted
        mid-run);
      - the sandbox (own EventBus + engine) is torn down in finally, so the run
        is isolated from the live engine and from concurrent runs.
    """
    sub = await deps.subscription_repo.get(sub_id)
    if sub is None:
        logger.warning("backtest_dispatch.subscription_not_found", sub_id=sub_id)
        return

    strategy_code = sub.strategy_code
    symbol = sub.symbol  # composite "{code}:{exchange}"
    interval = sub.interval.value

    await deps.backtest_repo.upsert_status(sub_id, strategy_code=strategy_code, status="running")

    sandbox: BacktestSandbox | None = None
    try:
        # Config lookup falls back across the three keyspaces a restart can
        # leave us in: a template-keyed config (explicit load, carries user
        # parameters) → the sub-keyed config rehydrate/reconcile register →
        # a bare default (strategy-class parameter defaults apply). Unknown
        # templates still fail in inject_strategy_into_sandbox's registry check.
        base_config = deps.strategy_app_service.get_config(
            strategy_code
        ) or deps.strategy_app_service.get_config(sub_id)
        if base_config is None:
            base_config = StrategyConfig(
                id=strategy_code,
                name=strategy_code,
                symbol=symbol,
                interval=interval,
            )

        start_date, end_date = await resolve_date_range(deps.bar_repo, symbol, interval)
        config = build_backtest_config(
            base_config, strategy_code, symbol, interval, start_date, end_date
        )

        sandbox = await build_backtest_sandbox()
        broker = await inject_strategy_into_sandbox(
            sandbox,
            base_config,
            strategy_code,
            sub_id,
            symbol,
            interval,
            initial_capital=config.initial_capital,
        )

        runner = BacktestAppService(
            event_bus=sandbox.event_bus,
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
        if sandbox is not None:
            await sandbox.aclose()
