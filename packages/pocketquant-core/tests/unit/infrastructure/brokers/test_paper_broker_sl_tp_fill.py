"""Unit tests for PaperBroker SL/TP auto-fill on BarCompletedEvent."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"


def _order(
    side: OrderSide,
    *,
    qty: float = 1.0,
    price: float = 100.0,
    sl: float | None = None,
    tp: float | None = None,
) -> OrderAggregate:
    return OrderAggregate.create(
        strategy_id="t",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        price=price,
        sl_price=sl,
        tp_price=tp,
    )


def _bar_event(
    *,
    high: float,
    low: float,
    close: float | None = None,
    symbol: str = _SYM,
) -> BarCompletedEvent:
    return BarCompletedEvent(
        symbol=symbol,
        interval="1m",
        bar_start=_T0,
        open=(high + low) / 2,
        high=high,
        low=low,
        close=close if close is not None else (high + low) / 2,
        volume=1.0,
    )


async def _broker(
    slippage: float = 0.0,
    with_bus: bool = True,
) -> tuple[PaperBroker, EventBus | None]:
    bus = EventBus() if with_bus else None
    b = PaperBroker(
        initial_balance=1_000_000.0,
        slippage_percent=slippage,
        fill_delay_ms=0,
        event_bus=bus,
    )
    await b.connect()
    return b, bus


async def test_no_event_bus_no_auto_fill() -> None:
    """PaperBroker(event_bus=None) skips bar subscription; positions never auto-close."""
    b, _ = await _broker(with_bus=False)
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    # Direct handler call — should still close because logic is independent of subscription.
    # But conceptually: with no bus, no event ever fires from the system.
    positions = await b.get_positions()
    assert len(positions) == 1


async def test_long_sl_fills_when_bar_low_below_sl() -> None:
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=99.0, low=97.0, close=98.5))
    positions = await b.get_positions()
    assert positions == []
    # 1 callback for entry + 1 for exit
    assert len(callbacks) == 2
    assert callbacks[-1].side == OrderSide.SELL
    assert callbacks[-1].filled_price == pytest.approx(98.0)


async def test_long_tp_fills_when_bar_high_above_tp() -> None:
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=105.0, low=99.0, close=104.5))
    assert await b.get_positions() == []
    assert callbacks[-1].side == OrderSide.SELL
    assert callbacks[-1].filled_price == pytest.approx(104.0)


async def test_long_both_hit_in_same_bar_sl_wins() -> None:
    """SL takes precedence when a single bar covers both SL and TP (worst-case contract)."""
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=105.0, low=97.0, close=101.0))
    assert await b.get_positions() == []
    # Only one exit fill emitted, at SL price.
    sells = [c for c in callbacks if c.side == OrderSide.SELL]
    assert len(sells) == 1
    assert sells[0].filled_price == pytest.approx(98.0)


async def test_short_sl_fills_when_bar_high_above_sl() -> None:
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    await b.submit_order(_order(OrderSide.SELL, sl=102.0, tp=96.0))
    await bus.publish(_bar_event(high=103.0, low=99.0, close=102.5))
    assert await b.get_positions() == []
    buys = [c for c in callbacks if c.side == OrderSide.BUY]
    assert len(buys) == 1
    assert buys[0].filled_price == pytest.approx(102.0)


async def test_short_tp_fills_when_bar_low_below_tp() -> None:
    b, bus = await _broker()
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    await b.submit_order(_order(OrderSide.SELL, sl=102.0, tp=96.0))
    await bus.publish(_bar_event(high=101.0, low=95.0, close=96.5))
    assert await b.get_positions() == []
    buys = [c for c in callbacks if c.side == OrderSide.BUY]
    assert buys[0].filled_price == pytest.approx(96.0)


async def test_fill_clears_state_so_subsequent_bars_dont_double_fire() -> None:
    b, bus = await _broker()
    assert bus is not None
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=99.0, low=97.0, close=98.5))
    assert await b.get_positions() == []
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    # Subsequent bar — no new exits.
    await bus.publish(_bar_event(high=110.0, low=95.0, close=100.0))
    assert callbacks == []


async def test_order_with_no_sl_tp_skipped() -> None:
    b, bus = await _broker()
    assert bus is not None
    await b.submit_order(_order(OrderSide.BUY))  # no SL/TP
    await bus.publish(_bar_event(high=200.0, low=1.0, close=100.0))
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].sl_price is None
    assert positions[0].tp_price is None


async def test_slippage_applied_to_synthetic_exit() -> None:
    """With non-zero slippage, SELL exit price = trigger * (1 - slippage)."""
    b, bus = await _broker(slippage=0.001)
    assert bus is not None
    callbacks: list = []
    await b.subscribe_order_updates(lambda r: callbacks.append(r))
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=99.0, low=97.0, close=98.5))
    exit_fill = [c for c in callbacks if c.side == OrderSide.SELL][0]
    assert exit_fill.filled_price == pytest.approx(98.0 * (1 - 0.001))


async def test_disconnect_unsubscribes() -> None:
    b, bus = await _broker()
    assert bus is not None
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await b.disconnect()
    # Bus no longer routes to this broker.
    await bus.publish(_bar_event(high=99.0, low=97.0, close=98.5))
    positions = await b.get_positions()
    assert len(positions) == 1  # still open
