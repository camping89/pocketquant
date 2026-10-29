from __future__ import annotations

import asyncio
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

_HEARTBEAT_S = 15.0


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

    # The engine catches its own errors and returns a failed result, so a failed run is
    # seen in the returned status, not as an exception. The except here catches faults
    # outside the engine (unknown strategy, a repo error) and flips the started doc to
    # failed so it cannot stay stuck.
    async def execute_and_persist(self, run_id: str, config_payload: dict[str, Any]) -> None:
        beat = asyncio.create_task(self._heartbeat(run_id))
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
        finally:
            beat.cancel()

    # Keeps the run out of the worker's orphan sweep while this task lives.
    async def _heartbeat(self, run_id: str) -> None:
        while True:
            try:
                await self._backtest_repo.touch_heartbeat(run_id)
            except Exception:
                logger.warning("backtest_execution.heartbeat_failed", run_id=run_id, exc_info=True)
            await asyncio.sleep(_HEARTBEAT_S)

    # A private sandbox (own EventBus and StrategyAppService) keeps replayed bars and
    # synthetic exit fills away from the live execution engine.
    async def run(
        self, config_payload: dict[str, Any], run_id: str | None = None
    ) -> BacktestResult:
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
