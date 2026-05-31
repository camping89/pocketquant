"""Characterization test pinning the strategy-injection round-trip contract.

This is the regression net for the Phase-7 extraction that replaces the three
private-member injection hacks (``run/handler.py``,
``backtest_strategy_loader.py``) with a public ``inject_prepared_strategy``
method on the execution engine.

The load-bearing behavior the public method MUST reproduce, verified here
against the CURRENT injection block:

  1. Round-trip: after injection, ``get_strategy(sid)`` returns the instance and
     ``unload_strategy(sid)`` clears it.
  2. The broker is **connected** after injection (the hack calls
     ``broker.connect()`` inside the lock when not already connected).
  3. ``strategy.on_start()`` fired exactly once (the hack awaits it inside the
     same critical section).

If the Phase-7 public method drops connect/on_start (a dict-only assignment),
assertions (2) and (3) fail here — that is the regression this test exists to
catch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.interfaces import IStrategy
from pocketquant.core.concepts.strategy.value_objects import Signal, StrategyConfig
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService


class _FakeBroker:
    """Minimal IBroker stand-in tracking connect() invocations."""

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


class _CountingStrategy(IStrategy):
    """Strategy recording on_start() invocations."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.on_start_calls = 0

    async def on_start(self) -> None:
        self.on_start_calls += 1
        await super().on_start()

    async def on_bar(self, bar: dict) -> Signal | None:
        return None


def _config(sid: str = "strat-1") -> StrategyConfig:
    return StrategyConfig(
        id=sid,
        name=sid,
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        trigger="bar",
        broker="paper",
    )


def _service() -> StrategyAppService:
    """Engine wired with mocks for the deps the injection path never touches."""
    return StrategyAppService(
        event_bus=EventBus(),
        broker_factory=AsyncMock(),
        order_app_service=AsyncMock(),
        position_app_service=AsyncMock(),
        risk_check_handler=AsyncMock(),
    )


async def _inject_current_way(
    svc: StrategyAppService,
    sid: str,
    strategy: IStrategy,
    broker: _FakeBroker,
    config: StrategyConfig,
) -> None:
    """Replicate the CURRENT private-member injection critical section verbatim.

    Mirrors ``RunBacktestHandler._load_strategy_for_backtest`` and
    ``load_strategy_for_backtest`` — connect + on_start happen inside the lock.
    Phase 7 replaces this block with ``svc.inject_prepared_strategy(...)``; this
    test pins what that method must do.
    """
    async with svc._lock:  # pyright: ignore[reportPrivateUsage]
        svc._strategies[sid] = strategy  # pyright: ignore[reportPrivateUsage]
        svc._brokers[sid] = broker  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
        svc._configs[sid] = config  # pyright: ignore[reportPrivateUsage]
        if not broker.is_connected:
            await broker.connect()
        await strategy.on_start()


@pytest.mark.asyncio
async def test_injection_roundtrip_get_then_unload() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()

    await _inject_current_way(svc, cfg.id, strat, broker, cfg)

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

    await _inject_current_way(svc, cfg.id, strat, broker, cfg)

    assert broker.is_connected is True
    assert broker.connect_calls == 1


@pytest.mark.asyncio
async def test_injection_invokes_on_start_once() -> None:
    svc = _service()
    cfg = _config()
    strat = _CountingStrategy(cfg)
    broker = _FakeBroker()

    await _inject_current_way(svc, cfg.id, strat, broker, cfg)

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

    await _inject_current_way(svc, cfg.id, strat, broker, cfg)

    # Guard already-connected: connect() not called a second time.
    assert broker.connect_calls == 1
