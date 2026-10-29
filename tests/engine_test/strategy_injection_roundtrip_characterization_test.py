# Pins the inject_prepared_strategy contract: round-trip with get_strategy and
# unload_strategy, broker connected, on_start fired exactly once inside the same critical
# section, get_config. A dict-only assignment that drops connect() and on_start() is the
# regression this guards.

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoClosedTrades,
    NoStoredBars,
)
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService


class _FakeBroker:
    def __init__(self) -> None:
        self._connected = False
        self.connect_calls = 0

    @property
    def name(self) -> str:
        return "paper"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self.connect_calls += 1
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False


class _CountingStrategy(IStrategyService):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.on_start_calls = 0

    async def on_start(self) -> None:
        self.on_start_calls += 1
        await super().on_start()

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return None


def _config(sid: str = "strat-1") -> StrategyConfig:
    return StrategyConfig(
        id=sid,
        name=sid,
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        broker="paper",
    )


# Mocks only the deps the injection path never touches.
def _service() -> StrategyAppService:
    return StrategyAppService(
        event_bus=EventBus(),
        broker_factory=AsyncMock(),
        order_app_service=AsyncMock(),
        position_app_service=AsyncMock(),
        risk_check_handler=AsyncMock(),
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_injection_roundtrip_get_then_unload() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()

    await svc.inject_prepared_strategy(cfg.id, strat, broker, cfg)  # pyright: ignore[reportArgumentType]

    assert svc.get_strategy(cfg.id) is strat
    await svc.unload_strategy(cfg.id)
    assert svc.get_strategy(cfg.id) is None


@pytest.mark.asyncio
async def test_injection_connects_broker() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()
    assert broker.is_connected is False

    await svc.inject_prepared_strategy(cfg.id, strat, broker, cfg)  # pyright: ignore[reportArgumentType]

    assert broker.is_connected is True
    assert broker.connect_calls == 1


@pytest.mark.asyncio
async def test_injection_invokes_on_start_once() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()

    await svc.inject_prepared_strategy(cfg.id, strat, broker, cfg)  # pyright: ignore[reportArgumentType]

    assert strat.on_start_calls == 1
    assert strat.is_running is True


@pytest.mark.asyncio
async def test_injection_does_not_reconnect_already_connected_broker() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()
    await broker.connect()
    assert broker.connect_calls == 1

    await svc.inject_prepared_strategy(cfg.id, strat, broker, cfg)  # pyright: ignore[reportArgumentType]

    # Guard already-connected: connect() not called a second time.
    assert broker.connect_calls == 1


@pytest.mark.asyncio
async def test_get_config_returns_registered_then_none_for_unknown() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()

    assert svc.get_config(cfg.id) is None
    await svc.inject_prepared_strategy(cfg.id, strat, broker, cfg)  # pyright: ignore[reportArgumentType]
    assert svc.get_config(cfg.id) is cfg
    assert svc.get_config("does-not-exist") is None
