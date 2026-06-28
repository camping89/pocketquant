"""Characterization test pinning PaperBroker MARKET + LIMIT fill behavior.

Complements the existing SL/TP auto-fill suite
(``test_paper_broker_sl_tp_fill.py``). This file pins the entry-fill state
machine that Phase 6 moves verbatim to ``pocketquant-infrastructure``:

  - MARKET order fills immediately at the signal price (+ slippage) and opens a
    LONG position without debiting cash (futures/margin model — balance moves
    only on realized close).
  - LIMIT order that does NOT cross stays pending (no position) until a later
    ``BarCompletedEvent`` whose range crosses the limit fills it.
  - SELL MARKET with no existing position opens a SHORT.

Behavior must be identical after the package move — assertions target
``PositionAggregate`` state + emitted ``OrderResult`` callbacks, not module
location.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import PositionSide
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"


def _order(
    side: OrderSide,
    order_type: OrderType,
    *,
    qty: float = 1.0,
    price: float = 100.0,
) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="t",
        symbol=_SYM,
        side=side,
        order_type=order_type,
        quantity=qty,
        price=price,
    )


def _bar_event(*, high: float, low: float, close: float) -> BarCompletedEvent:
    return BarCompletedEvent(
        symbol=_SYM,
        interval="1m",
        bar_start=_T0,
        open=(high + low) / 2,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


async def _broker(slippage: float = 0.0, with_bus: bool = True):
    bus = EventBus() if with_bus else None
    b = PaperBroker(
        initial_balance=1_000_000.0,
        slippage_percent=slippage,
        fill_delay_ms=0,
        event_bus=bus,
    )
    await b.connect()
    return b, bus


@pytest.mark.asyncio
async def test_market_buy_fills_immediately_and_opens_long() -> None:
    b, _ = await _broker()
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))

    result = await b.submit_order(_order(OrderSide.BUY, OrderType.MARKET, price=100.0))

    assert result.status == OrderStatus.FILLED
    assert result.filled_price == pytest.approx(100.0)
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].side == PositionSide.LONG
    assert len(callbacks) == 1


@pytest.mark.asyncio
async def test_market_buy_opens_position_without_debiting_cash() -> None:
    b, bus = await _broker(slippage=0.001)
    assert bus is not None

    result = await b.submit_order(_order(OrderSide.BUY, OrderType.MARKET, qty=2.0, price=100.0))

    expected_fill = 100.0 * (1 + 0.001)
    assert result.filled_price == pytest.approx(expected_fill)

    # futures: opening does not debit cash; available == total_equity (upl 0 at
    # entry, no price has moved yet).
    balance = await b.get_balance()
    assert balance.available_balance == pytest.approx(1_000_000.0)
    assert balance.total_equity == pytest.approx(1_000_000.0)

    # a completed bar marks the open position to its close → total_equity tracks
    # unrealized; available stays = _balance (price propagation lives in
    # _on_bar_completed, not get_balance).
    moved_price = expected_fill * 1.10
    await bus.publish(_bar_event(high=moved_price, low=expected_fill, close=moved_price))
    moved = await b.get_balance()
    assert moved.total_equity > 1_000_000.0
    assert moved.available_balance == pytest.approx(1_000_000.0)


@pytest.mark.asyncio
async def test_market_sell_opens_short_when_no_position() -> None:
    b, _ = await _broker()

    result = await b.submit_order(_order(OrderSide.SELL, OrderType.MARKET, price=100.0))

    assert result.status == OrderStatus.FILLED
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].side == PositionSide.SHORT


@pytest.mark.asyncio
async def test_limit_buy_pends_then_fills_on_crossing_bar() -> None:
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))

    # BUY LIMIT at 90 — no current price, so it queues pending (no immediate fill).
    result = await b.submit_order(_order(OrderSide.BUY, OrderType.LIMIT, price=90.0))
    assert result.status == OrderStatus.SUBMITTED
    assert await b.get_positions() == []

    # Bar whose low dips to/below 90 crosses the BUY LIMIT → fill.
    await bus.publish(_bar_event(high=95.0, low=89.0, close=92.0))

    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].side == PositionSide.LONG
    fills = [c for c in callbacks if c.status == OrderStatus.FILLED]
    assert len(fills) == 1
    assert fills[0].filled_price == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_limit_buy_stays_pending_when_bar_does_not_cross() -> None:
    b, bus = await _broker()
    assert bus is not None

    await b.submit_order(_order(OrderSide.BUY, OrderType.LIMIT, price=90.0))
    # Bar stays above the limit — no cross, order remains pending.
    await bus.publish(_bar_event(high=99.0, low=95.0, close=97.0))

    assert await b.get_positions() == []


@pytest.mark.asyncio
async def test_pending_limit_expires_on_expire_call() -> None:
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))

    await b.submit_order(_order(OrderSide.BUY, OrderType.LIMIT, price=90.0))
    expired = await b.expire_pending_orders()

    assert expired == 1
    assert any(c.status == OrderStatus.EXPIRED for c in callbacks)
