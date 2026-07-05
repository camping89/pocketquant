"""StrategyAppService._on_order_filled — routes fills to the owning strategy by id.

Bug #1 fix: a fill reaches ``strategy.on_order_filled`` so the strategy can reset
its open-direction and re-enter. Routing is by ``subscription_id`` (= strategy
id); a fill for an unknown id is a no-op.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.order import OrderFilledEvent, OrderSide
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService


class _RecordingStrategy(IStrategyService):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.fills: list[tuple[OrderSide, float]] = []

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return None

    async def on_order_filled(self, order, fill_price: float) -> None:
        self.fills.append((order.side, fill_price))


class _FakeBroker:
    def __init__(self) -> None:
        self._connected = False

    @property
    def name(self) -> str:
        return "paper"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False


def _config(sid: str) -> StrategyConfig:
    return StrategyConfig(
        id=sid,
        name=sid,
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        trigger="bar",
        broker="paper",
    )


def _service() -> StrategyAppService:
    return StrategyAppService(
        event_bus=EventBus(),
        broker_factory=AsyncMock(),
        order_app_service=AsyncMock(),
        position_app_service=AsyncMock(),
        risk_check_handler=AsyncMock(),
    )


def _event(sub_id: str, side: OrderSide, price: float) -> OrderFilledEvent:
    return OrderFilledEvent(
        order_id="o1",
        subscription_id=sub_id,
        symbol="BTCUSDT:BINANCE",
        side=side,
        filled_quantity=1.0,
        filled_price=price,
    )


@pytest.mark.asyncio
async def test_routes_fill_to_matching_strategy() -> None:
    svc = _service()
    cfg = _config("strat-A")
    strat = _RecordingStrategy(cfg)
    await svc.inject_prepared_strategy(cfg.id, strat, _FakeBroker(), cfg)  # pyright: ignore[reportArgumentType]

    await svc._on_order_filled(_event("strat-A", OrderSide.SELL, 99.5))

    assert strat.fills == [(OrderSide.SELL, 99.5)]


@pytest.mark.asyncio
async def test_unknown_subscription_id_is_noop() -> None:
    svc = _service()
    cfg = _config("strat-A")
    strat = _RecordingStrategy(cfg)
    await svc.inject_prepared_strategy(cfg.id, strat, _FakeBroker(), cfg)  # pyright: ignore[reportArgumentType]

    await svc._on_order_filled(_event("strat-UNKNOWN", OrderSide.SELL, 99.5))

    assert strat.fills == []


@pytest.mark.asyncio
async def test_fill_for_stopped_strategy_is_ignored() -> None:
    svc = _service()
    cfg = _config("strat-A")
    strat = _RecordingStrategy(cfg)
    await svc.inject_prepared_strategy(cfg.id, strat, _FakeBroker(), cfg)  # pyright: ignore[reportArgumentType]
    await svc.stop_strategy(cfg.id)

    await svc._on_order_filled(_event("strat-A", OrderSide.SELL, 99.5))

    assert strat.fills == []


@pytest.mark.asyncio
async def test_handler_swallows_strategy_exception() -> None:
    svc = _service()
    cfg = _config("strat-A")
    strat = _RecordingStrategy(cfg)

    async def _boom(order, fill_price: float) -> None:
        raise RuntimeError("strategy blew up")

    strat.on_order_filled = _boom  # type: ignore[method-assign]
    await svc.inject_prepared_strategy(cfg.id, strat, _FakeBroker(), cfg)  # pyright: ignore[reportArgumentType]

    # Must not propagate — one strategy's failure cannot break the event bus.
    await svc._on_order_filled(_event("strat-A", OrderSide.BUY, 100.0))
