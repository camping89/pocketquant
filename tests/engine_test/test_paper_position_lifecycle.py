"""A paper position never outlives its subscription or the process.

Unload drops the subscription's paper position and disconnects a broker no
other subscription holds; a restart closes every mirror row a venue does not
still hold.
"""

from __future__ import annotations

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self.created: list[PaperBrokerAdapter] = []
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        broker = PaperBrokerAdapter(fill_delay_ms=0, event_bus=self._bus)
        self.created.append(broker)
        return broker


class _Repo:
    def __init__(self, rows: list[PositionAggregate] | None = None) -> None:
        self.rows = {str(p.id): p for p in rows or []}

    async def save(self, item) -> None:  # noqa: ANN001
        if isinstance(item, PositionAggregate):
            self.rows[str(item.id)] = item

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [p for p in self.rows.values() if not p.is_closed]

    async def find_pending(self, limit: int = 500) -> list:
        return []


async def _engine() -> tuple[StrategyAppService, _Factory]:
    bus = EventBus()
    factory = _Factory(bus)
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=factory,  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _Repo()),  # type: ignore[arg-type]
        position_app_service=PositionAppService(bus, _Repo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
    )
    await engine.start()
    return engine, factory


def _config(sid: str) -> StrategyConfig:
    return StrategyConfig(id=sid, name="t", symbol=_SYM, interval="1m", broker="paper")


async def _open(broker: PaperBrokerAdapter, sid: str) -> None:
    await broker.submit_order(
        OrderAggregate.create(
            subscription_id=sid,
            symbol=_SYM,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=100.0,
            sl_price=90.0,
        )
    )


@pytest.mark.asyncio
async def test_unload_drops_the_position_and_disconnects_a_broker_no_one_holds() -> None:
    engine, factory = await _engine()
    await engine.load_strategy(_config("a"))
    broker = factory.created[0]
    await broker.connect()
    await _open(broker, "a")

    await engine.unload_strategy("a")

    assert await broker.get_positions() == []
    assert broker.is_connected is False


@pytest.mark.asyncio
async def test_unload_keeps_a_shared_broker_and_the_other_position() -> None:
    engine, factory = await _engine()
    await engine.load_strategy(_config("a"))
    await engine.load_strategy(_config("b"))
    broker = factory.created[0]
    await broker.connect()
    await _open(broker, "a")
    await _open(broker, "b")

    await engine.unload_strategy("a")

    assert [p.subscription_id for p in await broker.get_positions()] == ["b"]
    assert broker.is_connected is True


@pytest.mark.asyncio
async def test_boot_closes_paper_rows_and_keeps_venue_rows() -> None:
    def row(sid: str) -> PositionAggregate:
        return PositionAggregate.open(
            subscription_id=sid, symbol=_SYM, side=PositionSide.LONG, entry_price=1.0, quantity=1.0
        )

    repo = _Repo([row("paper-sub"), row("venue-sub")])
    mirror = PositionAppService(EventBus(), repo)  # type: ignore[arg-type]

    await mirror.start(frozenset({"venue-sub"}))

    assert [p.subscription_id for p in await repo.find_open()] == ["venue-sub"]
    assert mirror.get("paper-sub") is None
    assert mirror.get("venue-sub") is not None
