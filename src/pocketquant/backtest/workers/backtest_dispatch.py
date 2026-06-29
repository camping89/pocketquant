"""Backtest dispatch — single ad-hoc run setup-and-execute.

Centralizes the sandbox isolation + PaperBroker wiring so the route's spawned
task has one place that owns engine setup. Backtests run in their own sandbox,
never on the live execution engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.engine.backtest_engine_sandbox import build_backtest_sandbox
from pocketquant.backtest.models.backtest_config import BacktestConfig
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

logger = get_logger(__name__)


@dataclass
class BacktestDispatchDeps:
    bar_repo: BarRepository
    backtest_repo: BacktestRepository
    order_repo: BacktestOrderRepository
    trade_repo: BacktestTradeRepository


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


async def run_single(
    deps: BacktestDispatchDeps,
    config_payload: dict[str, Any],
    run_id: str | None = None,
) -> BacktestResult:
    """Execute one ad-hoc backtest and persist results to backtest_* collections.

    Runs in an isolated sandbox (own EventBus + StrategyAppService) so replayed
    bars and synthetic exit fills never reach the live execution engine, and the
    strategy is injected under its own id then torn down with the sandbox.

    ``run_id`` (route-allocated) is threaded into the engine so the persisted run
    doc and its orders/trades all share the id the started doc was created under.
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
        return await runner.run(config, run_id=run_id)
    finally:
        await sandbox.aclose()
