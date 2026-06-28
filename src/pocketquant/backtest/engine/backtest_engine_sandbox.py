"""Per-run isolated engine stack for backtests.

A backtest must not share the live execution engine's EventBus. The live
``StrategyAppService``/``PositionAppService`` subscribe to ``BarCompletedEvent``
and ``OrderFilledEvent`` on the application-wide bus; replaying historical bars
or publishing synthetic exit fills onto that bus would drive live handlers
(phantom positions, bar dispatch to unrelated strategies) and let concurrent
optimization runs cross-talk.

Each sandbox builds a fresh ``EventBus`` and a ``StrategyAppService`` bound to it
via a **local** ``EventRegistry`` (so handler bindings don't accumulate in the
process-global registry across runs). Order/position trackers are throwaway
in-memory instances; the position tracker is deliberately **not started**, so it
registers no handlers — the PaperBroker is the position source of truth during a
backtest, and the strategy's own one-position cap governs re-entry. Trades are
built by the ``BacktestResultCollector`` from broker fill callbacks, independent
of this bus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus, EventRegistry
from pocketquant.core.domain.brokers.interfaces import IBroker
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler

logger = get_logger(__name__)


class _InMemoryOrderRepo:
    def __init__(self) -> None:
        self._items: dict[str, OrderAggregate] = {}

    async def save(self, order: OrderAggregate) -> None:
        self._items[str(order.id)] = order

    async def get(self, order_id: str) -> OrderAggregate | None:
        return self._items.get(order_id)

    async def find_by_subscription(
        self, subscription_id: str, limit: int = 1000
    ) -> list[OrderAggregate]:
        return [o for o in self._items.values() if o.subscription_id == subscription_id][:limit]

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        return []


class _InMemoryPositionRepo:
    def __init__(self) -> None:
        self._items: dict[str, PositionAggregate] = {}

    async def save(self, position: PositionAggregate) -> None:
        self._items[str(position.id)] = position

    async def get(self, position_id: str) -> PositionAggregate | None:
        return self._items.get(position_id)

    async def get_by_subscription(self, subscription_id: str) -> PositionAggregate | None:
        for p in self._items.values():
            if p.subscription_id == subscription_id and not p.is_closed:
                return p
        return None

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [p for p in self._items.values() if not p.is_closed][:limit]


class _SingleBrokerFactory:
    """Returns the run's pre-built broker; the inject path never asks the factory.

    StrategyAppService only consults the factory in ``load_strategy`` (live
    path). Backtests inject a prepared broker, so this is a safety stand-in.
    """

    def __init__(self, broker: IBroker) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBroker:
        return self._broker

    @staticmethod
    def get_available_types() -> list[str]:
        return ["paper"]


@dataclass
class BacktestSandbox:
    """An isolated engine stack for one backtest run.

    ``event_bus`` and ``strategy_app_service`` are private to this run. Build a
    broker with ``create_broker`` (wired to this bus), inject the strategy into
    ``strategy_app_service``, run via ``BacktestAppService(event_bus=...)``, then
    ``aclose()`` to unload strategies and release bus bindings.
    """

    event_bus: EventBus
    strategy_app_service: StrategyAppService
    _broker: PaperBroker | None = None

    def create_broker(
        self,
        initial_balance: float,
        slippage_percent: float = 0.0,
        fill_delay_ms: int = 0,
        currency: str = "USDT",
    ) -> PaperBroker:
        broker = PaperBroker(
            initial_balance=initial_balance,
            slippage_percent=slippage_percent,
            fill_delay_ms=fill_delay_ms,
            currency=currency,
            event_bus=self.event_bus,
        )
        self._broker = broker
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


async def build_backtest_sandbox(
    default_broker_config: dict[str, Any] | None = None,
) -> BacktestSandbox:
    """Create an isolated engine stack bound to a fresh per-run EventBus.

    The StrategyAppService is started against a local EventRegistry so its
    handler bindings live and die with this run's bus.
    """
    bus = EventBus()
    placeholder_broker = PaperBroker(event_bus=bus)
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=_SingleBrokerFactory(placeholder_broker),  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _InMemoryOrderRepo()),  # type: ignore[arg-type]
        position_app_service=PositionAppService(bus, _InMemoryPositionRepo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
        default_broker_config=default_broker_config,
    )
    await engine.start(registry=EventRegistry())
    return BacktestSandbox(event_bus=bus, strategy_app_service=engine)
