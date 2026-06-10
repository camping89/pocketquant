"""Tests for PaperBroker OrderEvent emission (Phase 2 contract)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import (
    clear_simulation_time,
    set_simulation_time,
)
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker


@pytest.fixture(autouse=True)
def reset_sim() -> None:
    clear_simulation_time()
    yield
    clear_simulation_time()


@pytest.fixture
async def broker() -> PaperBroker:
    bus = EventBus()
    b = PaperBroker(initial_balance=100_000, slippage_percent=0, fill_delay_ms=0, event_bus=bus)
    await b.connect()
    b.set_current_price("BTC:BIN", 65000)
    return b


@pytest.mark.asyncio
async def test_market_fill_emits_submitted_then_filled(broker: PaperBroker) -> None:
    events: list = []
    await broker.subscribe_order_event(lambda oid, ev: events.append((oid, ev)))
    o = OrderAggregate.create(
        subscription_id="s",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
    )
    await broker.submit_order(o)
    log = broker.get_order_events(o.id)
    assert [e.to_status for e in log] == [OrderStatus.SUBMITTED, OrderStatus.FILLED]
    assert [e.reason for e in log] == ["submit", "market_fill"]
    # Callback received both
    assert [ev.to_status for _oid, ev in events] == [OrderStatus.SUBMITTED, OrderStatus.FILLED]


@pytest.mark.asyncio
async def test_reject_insufficient_balance_emits_submitted_then_rejected(
    broker: PaperBroker,
) -> None:
    huge = OrderAggregate.create(
        subscription_id="s",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=999.0,
    )
    result = await broker.submit_order(huge)
    assert result.status == OrderStatus.REJECTED
    log = broker.get_order_events(huge.id)
    assert [e.to_status for e in log] == [OrderStatus.SUBMITTED, OrderStatus.REJECTED]
    assert log[1].reason == "insufficient_balance"


@pytest.mark.asyncio
async def test_event_timestamps_use_simulation_time(broker: PaperBroker) -> None:
    sim_t = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    set_simulation_time(sim_t)
    o = OrderAggregate.create(
        subscription_id="s",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
    )
    await broker.submit_order(o)
    log = broker.get_order_events(o.id)
    assert all(ev.timestamp == sim_t for ev in log)


@pytest.mark.asyncio
async def test_sl_autofill_synthetic_order_carries_auto_sl_reason() -> None:
    bus = EventBus()
    broker = PaperBroker(
        initial_balance=100_000, slippage_percent=0, fill_delay_ms=0, event_bus=bus
    )
    await broker.connect()
    broker.set_current_price("BTC:BIN", 65000)
    events: list = []
    await broker.subscribe_order_event(lambda oid, ev: events.append((oid, ev)))
    o = OrderAggregate.create(
        subscription_id="s",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
        sl_price=63000,
        tp_price=70000,
    )
    await broker.submit_order(o)
    events.clear()  # focus on SL emission
    bar = BarCompletedEvent(
        symbol="BTC:BIN",
        interval="1m",
        bar_start=datetime.now(UTC),
        open=64000,
        high=64500,
        low=62000,
        close=63500,
        volume=1.0,
    )
    await bus.publish(bar)
    # Synthetic exit order should emit SUBMITTED + FILLED(auto_sl)
    sl_events = [ev for _oid, ev in events if ev.reason == "auto_sl"]
    assert len(sl_events) == 1


@pytest.mark.asyncio
async def test_subscribe_callback_receives_every_event_in_order(broker: PaperBroker) -> None:
    received: list = []
    await broker.subscribe_order_event(lambda oid, ev: received.append(ev.to_status))
    o = OrderAggregate.create(
        subscription_id="s",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
    )
    await broker.submit_order(o)
    assert received == [OrderStatus.SUBMITTED, OrderStatus.FILLED]
