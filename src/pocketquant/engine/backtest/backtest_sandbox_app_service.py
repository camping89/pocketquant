from __future__ import annotations

from dataclasses import dataclass

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.core.domain.trading import commission_model_for
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


class _InMemoryOrderRepo:
    def __init__(self) -> None:
        self._items: dict[str, OrderAggregate] = {}

    async def save(self, order: OrderAggregate) -> None:
        self._items[str(order.id)] = order

    async def get(self, order_id: str) -> OrderAggregate | None:
        return self._items.get(order_id)

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        return []


class _InMemoryPositionRepo:
    def __init__(self) -> None:
        self._items: dict[str, PositionAggregate] = {}

    async def save(self, position: PositionAggregate) -> None:
        self._items[str(position.id)] = position

    async def get(self, position_id: str) -> PositionAggregate | None:
        return self._items.get(position_id)

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [p for p in self._items.values() if not p.is_closed][:limit]

    async def delete_open_by_subscription(self, subscription_id: str) -> int:
        gone = [k for k, p in self._items.items() if p.subscription_id == subscription_id]
        for key in gone:
            del self._items[key]
        return len(gone)


class NoStoredBars:
    async def find(self, *args: object, **kwargs: object) -> list[Bar]:
        return []


class NoClosedTrades:
    async def realized_net(self, run_ids: list[str]) -> float:
        return 0.0


class Continuous24x7CalendarFactory:
    async def for_symbol(self, symbol: str) -> ITradingCalendarPort:
        return Continuous24x7Calendar()


# StrategyAppService asks the factory only in load_strategy (the live path).
# Backtests inject a prepared broker, so this is a safety stand-in.
class _SingleBrokerFactory:
    def __init__(self, broker: IBrokerPort) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
        return self._broker


@dataclass
class BacktestSandboxAppService:
    event_bus: EventBus
    strategy_app_service: StrategyAppService

    def create_broker(
        self,
        initial_balance: float,
        slippage_percent: float = 0.0,
        commission_bps: float = 0.0,
        contract_spec: ContractSpec = LINEAR_SPEC,
        spread: float = 0.0,
    ) -> PaperBrokerAdapter:
        broker = PaperBrokerAdapter(
            initial_balance=initial_balance,
            slippage_percent=slippage_percent,
            fill_delay_ms=0,
            event_bus=self.event_bus,
            commission_model=commission_model_for(
                contract_spec.commission_per_contract, commission_bps
            ),
            contract_spec=contract_spec,
            spread=spread,
        )
        # Late-bind the broker into the factory so any (unexpected) factory
        # lookup returns this run's broker rather than a foreign one.
        self.strategy_app_service._broker_factory = _SingleBrokerFactory(broker)  # type: ignore[assignment]
        return broker

    async def aclose(self) -> None:
        for sid in self.strategy_app_service.loaded_strategy_ids():
            try:
                await self.strategy_app_service.unload_strategy(sid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("backtest_sandbox.unload_failed", sid=sid, error=str(exc))


# A backtest must not share the live EventBus: replayed bars or synthetic exit fills
# would drive live handlers (phantom positions, bars sent to unrelated strategies)
# and let concurrent runs cross-talk. The position tracker is deliberately not
# started, so it registers no handlers: the paper broker is the position source of
# truth during a backtest.
async def build_backtest_sandbox() -> BacktestSandboxAppService:
    bus = EventBus()
    placeholder_broker = PaperBrokerAdapter(event_bus=bus)
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=_SingleBrokerFactory(placeholder_broker),  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _InMemoryOrderRepo()),  # type: ignore[arg-type]
        position_app_service=PositionAppService(bus, _InMemoryPositionRepo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )
    await engine.start()
    return BacktestSandboxAppService(event_bus=bus, strategy_app_service=engine)
