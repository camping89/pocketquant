"""Tests for PaperBroker LIMIT pending queue + expire_pending_orders (Phase 2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker


@pytest.fixture(autouse=True)
def reset_sim() -> None:
    clear_simulation_time()
    yield
    clear_simulation_time()


@pytest.fixture
async def setup() -> tuple[PaperBroker, EventBus]:
    bus = EventBus()
    b = PaperBroker(initial_balance=100_000, slippage_percent=0, fill_delay_ms=0,
                    event_bus=bus)
    await b.connect()
    b.set_current_price("BTC:BIN", 65000)
    return b, bus


@pytest.mark.asyncio
async def test_unreachable_limit_remains_submitted_then_expires_at_end_of_run(
    setup: tuple[PaperBroker, EventBus],
) -> None:
    broker, _ = setup
    # BUY LIMIT below current price → would be reachable. Use unreachable: below current.
    # Wait — BUY LIMIT fills when market <= limit. To be UNREACHABLE for BUY: limit < market.
    o = OrderAggregate.create(strategy_id="s", symbol="BTC:BIN", side=OrderSide.BUY,
                              order_type=OrderType.LIMIT, quantity=0.01, price=50000)
    r = await broker.submit_order(o)
    assert r.status == OrderStatus.SUBMITTED
    log = broker.get_order_events(o.id)
    assert log[-1].to_status == OrderStatus.SUBMITTED  # only initial event so far

    n = await broker.expire_pending_orders()
    assert n == 1
    log = broker.get_order_events(o.id)
    assert log[-1].to_status == OrderStatus.EXPIRED
    assert log[-1].reason == "end_of_run"


@pytest.mark.asyncio
async def test_reachable_limit_fills_immediately(setup: tuple[PaperBroker, EventBus]) -> None:
    broker, _ = setup
    # BUY LIMIT at 70000 when current is 65000: 65000 <= 70000, fills immediately.
    o = OrderAggregate.create(strategy_id="s", symbol="BTC:BIN", side=OrderSide.BUY,
                              order_type=OrderType.LIMIT, quantity=0.01, price=70000)
    r = await broker.submit_order(o)
    assert r.status == OrderStatus.FILLED
    assert broker.get_order_events(o.id)[-1].reason == "limit_immediate"


@pytest.mark.asyncio
async def test_pending_limit_fills_on_later_bar_with_limit_cross_reason(
    setup: tuple[PaperBroker, EventBus],
) -> None:
    broker, bus = setup
    # BUY LIMIT @ 60000 (below current 65000) → pending.
    o = OrderAggregate.create(strategy_id="s", symbol="BTC:BIN", side=OrderSide.BUY,
                              order_type=OrderType.LIMIT, quantity=0.01, price=60000)
    await broker.submit_order(o)
    # Bar with low 59000 crosses BUY LIMIT 60000.
    bar = BarCompletedEvent(symbol="BTC:BIN", interval="1m",
                            bar_start=datetime.now(UTC),
                            open=65000, high=65000, low=59000, close=63000, volume=1.0)
    await bus.publish(bar)
    log = broker.get_order_events(o.id)
    assert log[-1].to_status == OrderStatus.FILLED
    assert log[-1].reason == "limit_cross"


@pytest.mark.asyncio
async def test_cancel_pending_limit(setup: tuple[PaperBroker, EventBus]) -> None:
    broker, _ = setup
    o = OrderAggregate.create(strategy_id="s", symbol="BTC:BIN", side=OrderSide.BUY,
                              order_type=OrderType.LIMIT, quantity=0.01, price=50000)
    r = await broker.submit_order(o)
    ok = await broker.cancel_order(r.broker_order_id)
    assert ok is True
    log = broker.get_order_events(o.id)
    assert log[-1].to_status == OrderStatus.CANCELLED
    assert log[-1].reason == "user_cancel"


@pytest.mark.asyncio
async def test_cancel_unknown_broker_id_is_idempotent(setup: tuple[PaperBroker, EventBus]) -> None:
    broker, _ = setup
    # cancel_order on never-seen id should return True (idempotent, no state change)
    assert await broker.cancel_order("nonexistent") is True


@pytest.mark.asyncio
async def test_pending_limit_doesnt_cross_in_neutral_bar(
    setup: tuple[PaperBroker, EventBus],
) -> None:
    broker, bus = setup
    o = OrderAggregate.create(strategy_id="s", symbol="BTC:BIN", side=OrderSide.BUY,
                              order_type=OrderType.LIMIT, quantity=0.01, price=50000)
    await broker.submit_order(o)
    # Bar low 60000 > limit 50000 — doesn't cross
    bar = BarCompletedEvent(symbol="BTC:BIN", interval="1m",
                            bar_start=datetime.now(UTC),
                            open=65000, high=66000, low=60000, close=63000, volume=1.0)
    await bus.publish(bar)
    log = broker.get_order_events(o.id)
    # Still SUBMITTED (no terminal event yet)
    assert log[-1].to_status == OrderStatus.SUBMITTED


@pytest.mark.asyncio
async def test_sell_limit_fills_on_high_crossing(setup: tuple[PaperBroker, EventBus]) -> None:
    broker, bus = setup
    # SELL LIMIT @ 70000, current 65000 (pending: not crossed yet)
    o = OrderAggregate.create(strategy_id="s", symbol="BTC:BIN", side=OrderSide.SELL,
                              order_type=OrderType.LIMIT, quantity=0.01, price=70000)
    r = await broker.submit_order(o)
    assert r.status == OrderStatus.SUBMITTED
    # Bar high 71000 crosses SELL LIMIT 70000
    bar = BarCompletedEvent(symbol="BTC:BIN", interval="1m",
                            bar_start=datetime.now(UTC),
                            open=68000, high=71000, low=67000, close=70500, volume=1.0)
    await bus.publish(bar)
    log = broker.get_order_events(o.id)
    assert log[-1].to_status == OrderStatus.FILLED
    assert log[-1].reason == "limit_cross"
