"""Backtest execution service — runs one ad-hoc backtest to completion.

The body of the ``asyncio.create_task`` the route spawns. Lives in the
``backtest`` layer (no fastapi import) so the route only allocates the run id,
persists the started doc, and hands off here. Each run gets its own sandbox,
never the live execution engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest import BacktestConfig, BacktestResult
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.symbol import ContractSpec
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
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
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper
from pocketquant.engine.backtest.backtest_app_service import BacktestAppService
from pocketquant.engine.backtest.backtest_sandbox_app_service import build_backtest_sandbox

logger = get_logger(__name__)


def _config_from_dict(payload: dict[str, Any], contract_spec: ContractSpec) -> BacktestConfig:
    return BacktestConfig(
        strategy_code=payload["strategy_code"],
        symbol=payload["symbol"],
        interval=payload["interval"],
        start_date=datetime.fromisoformat(payload["start_date"]),
        end_date=datetime.fromisoformat(payload["end_date"]),
        initial_capital=payload.get("initial_capital", 10_000.0),
        slippage_bps=payload.get("slippage_bps", 0.5),
        commission_bps=payload.get("commission_bps", 3.0),
        spread=payload.get("spread", 0.0),
        parameters=payload.get("parameters") or {},
        name=payload.get("name"),
        contract_spec=contract_spec,
    )


class BacktestExecutionService:
    def __init__(
        self,
        bar_repository: BarRepository,
        backtest_repository: BacktestRepository,
        backtest_order_repository: BacktestOrderRepository,
        backtest_trade_repository: BacktestTradeRepository,
        calendar_factory: TradingCalendarFactory,
        symbol_lookup: SymbolLookupHelper,
    ) -> None:
        self._bar_repo = bar_repository
        self._backtest_repo = backtest_repository
        self._order_repo = backtest_order_repository
        self._trade_repo = backtest_trade_repository
        self._calendar_factory = calendar_factory
        self._symbol_lookup = symbol_lookup

    async def execute_and_persist(self, run_id: str, config_payload: dict[str, Any]) -> None:
        """Run the engine for ``run_id`` and let it persist the run/orders/trades.

        The engine catches its own errors and RETURNS a ``failed`` result (it
        never re-raises), so a failed engine run is detected by inspecting the
        returned status — not by an exception. The ``except`` here only catches
        faults OUTSIDE the engine (e.g. an unknown strategy, a transient repo
        error), and flips the started doc to ``failed`` so it can't stay stuck.
        """
        try:
            result = await self.run(config_payload, run_id=run_id)
            if result.status == "failed":
                logger.warning(
                    "backtest_execution.engine_failed",
                    run_id=run_id,
                    error=result.error_message,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("backtest_execution.dispatch_failed", run_id=run_id, error=str(exc))
            await self._backtest_repo.mark_failed(run_id, str(exc)[:500])

    async def run(
        self, config_payload: dict[str, Any], run_id: str | None = None
    ) -> BacktestResult:
        """Execute one backtest and persist results to the backtest_* collections.

        Runs in an isolated sandbox (own EventBus + StrategyAppService) so replayed
        bars and synthetic exit fills never reach the live execution engine, and the
        strategy is injected under its own id then torn down with the sandbox.
        """
        contract_spec = await self._symbol_lookup.contract_spec(config_payload["symbol"])
        config = _config_from_dict(config_payload, contract_spec)

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
            broker="paper",
            parameters={**config.parameters},
            contract_spec=config.contract_spec,
        )

        sandbox = await build_backtest_sandbox()
        try:
            broker = sandbox.create_broker(
                initial_balance=config.initial_capital,
                slippage_percent=config.slippage_percent,
                commission_bps=config.commission_bps,
                contract_spec=config.contract_spec,
                spread=config.spread,
            )
            strategy_instance = strategy_class(strategy_cfg)
            await sandbox.strategy_app_service.inject_prepared_strategy(
                strategy_instance.id, strategy_instance, broker, strategy_instance.config
            )

            runner = BacktestAppService(
                event_bus=sandbox.event_bus,
                broker=broker,
                backtest_repository=self._backtest_repo,
                bar_repository=self._bar_repo,
                calendar=await self._calendar_factory.for_symbol(config.symbol),
                order_repository=self._order_repo,
                trade_repository=self._trade_repo,
            )
            return await runner.run(config, run_id=run_id)
        finally:
            await sandbox.aclose()
