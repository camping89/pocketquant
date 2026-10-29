from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionSide
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"


def _order(
    side: OrderSide,
    order_type: OrderType = OrderType.MARKET,
    *,
    qty: float = 1.0,
    price: float = 100.0,
    sl: float | None = None,
    tp: float | None = None,
) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="t",
        symbol=_SYM,
        side=side,
        order_type=order_type,
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
    open: float | None = None,
    interval: str = "1m",
) -> BarCompletedEvent:
    return BarCompletedEvent(
        symbol=symbol,
        interval=interval,
        bar_start=_T0,
        open=open if open is not None else (high + low) / 2,
        high=high,
        low=low,
        close=close if close is not None else (high + low) / 2,
        volume=1.0,
    )


async def _broker(
    slippage: float = 0.0,
    with_bus: bool = True,
) -> tuple[PaperBrokerAdapter, EventBus | None]:
    bus = EventBus() if with_bus else None
    b = PaperBrokerAdapter(
        initial_balance=1_000_000.0,
        slippage_percent=slippage,
        fill_delay_ms=0,
        event_bus=bus,
    )
    await b.connect()
    return b, bus


async def test_no_event_bus_no_auto_fill() -> None:
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


# Worst-case contract: SL wins when one bar covers both SL and TP.
async def test_long_both_hit_in_same_bar_sl_wins() -> None:
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


# The strategy's on_order_filled reset depends on this exit event reaching the bus: entry
# fills publish via order_app_service, synthetic exits do not.
async def test_synthetic_exit_publishes_order_filled_event() -> None:
    b, bus = await _broker()
    assert bus is not None
    events: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, lambda e: events.append(e))
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))  # subscription_id="t"
    await bus.publish(_bar_event(high=99.0, low=97.0, close=98.5))  # hits SL

    assert len(events) == 1
    ev = events[0]
    assert ev.subscription_id == "t"
    assert ev.side == OrderSide.SELL  # opposite of the LONG entry
    assert ev.filled_price == pytest.approx(98.0)


# A closed position lingers in the broker's dict under its key; without the closed-position
# guard the re-entry BUY raises 'Cannot add to closed position' and the multi-trade loop
# breaks.
async def test_reentry_after_close_opens_fresh_position() -> None:
    b, bus = await _broker()
    assert bus is not None
    # Open long, then SL closes it.
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=99.0, low=97.0, close=98.5))
    assert await b.get_positions() == []

    # Re-entry must succeed and open a new live position.
    result = await b.submit_order(_order(OrderSide.BUY, price=100.0, sl=98.0, tp=104.0))
    assert result.status == OrderStatus.FILLED
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == pytest.approx(1.0)


async def test_short_reentry_after_close_opens_fresh_position() -> None:
    b, bus = await _broker()
    assert bus is not None
    await b.submit_order(_order(OrderSide.SELL, sl=102.0, tp=96.0))
    await bus.publish(_bar_event(high=103.0, low=99.0, close=102.5))  # hits SHORT SL
    assert await b.get_positions() == []

    result = await b.submit_order(_order(OrderSide.SELL, price=100.0, sl=102.0, tp=96.0))
    assert result.status == OrderStatus.FILLED
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == pytest.approx(1.0)


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


async def test_market_sell_opens_short_when_no_position() -> None:
    b, _ = await _broker()

    result = await b.submit_order(_order(OrderSide.SELL, OrderType.MARKET, price=100.0))

    assert result.status == OrderStatus.FILLED
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].side == PositionSide.SHORT


async def _fills(b: PaperBrokerAdapter) -> list:
    fills: list = []
    await b.subscribe_order_updates(lambda r: fills.append(r))
    return fills


# A 4h bar's range predates an entry made inside it, so only the 1m stream exits.
async def test_coarser_bar_does_not_close_but_next_1m_does() -> None:
    b, bus = await _broker()
    assert bus is not None
    fills = await _fills(b)
    await bus.publish(_bar_event(high=100.2, low=99.8))
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))

    await bus.publish(_bar_event(high=105.0, low=97.0, interval="4h"))
    assert len(await b.get_positions()) == 1

    await bus.publish(_bar_event(high=100.5, low=97.5))
    assert await b.get_positions() == []
    assert fills[-1].filled_price == pytest.approx(98.0)


# A symbol that only gets 15m bars still exits while another symbol streams 1m.
async def test_finest_interval_is_per_symbol() -> None:
    b, bus = await _broker()
    assert bus is not None
    other = "ETHUSDT:BINANCE"
    await bus.publish(_bar_event(high=100.2, low=99.8))
    await b.submit_order(
        OrderAggregate.create(
            subscription_id="e",
            symbol=other,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=100.0,
            sl_price=98.0,
        )
    )
    await bus.publish(_bar_event(high=99.0, low=97.0, symbol=other, interval="15m"))
    assert await b.get_positions() == []


# The bar that triggered an entry predates it; the next bar checks the position.
async def test_signal_bar_does_not_close_entry_made_by_its_handler() -> None:
    b, bus = await _broker()
    assert bus is not None
    entered: list[bool] = []

    async def strategy(event: BarCompletedEvent) -> None:
        if not entered:
            entered.append(True)
            await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))

    # Strategy handlers subscribe before the broker, as in StrategyAppService.
    await b.disconnect()
    bus.subscribe(BarCompletedEvent, strategy)
    await b.connect()

    await bus.publish(_bar_event(high=101.0, low=97.0))
    assert len(await b.get_positions()) == 1

    await bus.publish(_bar_event(high=101.0, low=97.0))
    assert await b.get_positions() == []


async def test_long_sl_gap_fills_at_open() -> None:
    b, bus = await _broker(slippage=0.001)
    assert bus is not None
    fills = await _fills(b)
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=97.0, low=95.0, open=96.0))
    assert fills[-1].filled_price == pytest.approx(96.0 * 0.999)


async def test_long_tp_gap_fills_at_open() -> None:
    b, bus = await _broker()
    assert bus is not None
    fills = await _fills(b)
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=107.0, low=105.0, open=106.0))
    assert fills[-1].filled_price == pytest.approx(106.0)


# The open is the first trade, so a TP it already passed fills before a later SL touch.
async def test_open_past_tp_beats_intrabar_sl() -> None:
    b, bus = await _broker()
    assert bus is not None
    fills = await _fills(b)
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=105.0, low=97.0, open=105.0))
    sells = [f for f in fills if f.side == OrderSide.SELL]
    assert len(sells) == 1
    assert sells[0].filled_price == pytest.approx(105.0)


async def test_long_sl_inside_range_fills_at_level() -> None:
    b, bus = await _broker()
    assert bus is not None
    fills = await _fills(b)
    await b.submit_order(_order(OrderSide.BUY, sl=98.0, tp=104.0))
    await bus.publish(_bar_event(high=99.5, low=97.0, open=99.0))
    assert fills[-1].filled_price == pytest.approx(98.0)


# ES SHORT at the 2026-10-25 CME reopen: the bar opened at 7690, past SL 7680.92.
async def test_short_sl_reopen_gap_matches_prod() -> None:
    b, bus = await _broker(slippage=0.00005)
    assert bus is not None
    fills = await _fills(b)
    await b.submit_order(_order(OrderSide.SELL, price=7665.87, sl=7680.92, tp=7651.25))
    await bus.publish(_bar_event(high=7698.5, low=7690.0, open=7690.0))
    assert fills[-1].filled_price == pytest.approx(7690.0 * 1.00005)


async def test_a_limit_order_is_rejected() -> None:
    b, _ = await _broker()

    result = await b.submit_order(_order(OrderSide.BUY, OrderType.LIMIT, price=90.0))

    assert result.status == OrderStatus.REJECTED
    assert await b.get_positions() == []
