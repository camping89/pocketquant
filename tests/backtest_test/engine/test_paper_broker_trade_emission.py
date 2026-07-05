"""PaperBrokerAdapter forwards TradeClosedEvent via subscribe_trades.

Model: futures, initial 10_000, slippage 0, commission 10 bps (0.001). A trade
closure fires on every reduce/close, carrying chunk pnl (non-cumulative), the
entry-portion + exit commission, direction as PositionSide.name, and the entry/
exit order ids. Ordering contract: the fill OrderResult is delivered BEFORE the
TradeClosedEvent so a subscriber can back-link the exit order.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.trading import PercentageCommissionModel
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"
_INITIAL = 10_000.0
_BPS = 10.0  # 0.1%


def _order(
    side: OrderSide,
    *,
    qty: float,
    price: float,
    order_type: OrderType = OrderType.MARKET,
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


def _bar(*, high: float, low: float, close: float) -> BarCompletedEvent:
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


async def _broker() -> tuple[PaperBrokerAdapter, EventBus, list[TradeClosedEvent]]:
    bus = EventBus()
    b = PaperBrokerAdapter(
        initial_balance=_INITIAL,
        slippage_percent=0.0,
        fill_delay_ms=0,
        event_bus=bus,
        commission_model=PercentageCommissionModel(bps=_BPS),
    )
    trades: list[TradeClosedEvent] = []
    await b.subscribe_trades(lambda t: trades.append(t))
    await b.connect()
    return b, bus, trades


async def test_full_close_emits_one_trade_with_pnl_commission_direction_orders() -> None:
    b, _bus, trades = await _broker()
    entry = _order(OrderSide.BUY, qty=10, price=100.0)
    exit_ = _order(OrderSide.SELL, qty=10, price=110.0)
    await b.submit_order(entry)
    await b.submit_order(exit_)

    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "LONG"
    assert t.quantity == 10.0
    assert t.entry_price == 100.0
    assert t.exit_price == 110.0
    assert t.pnl == pytest.approx(100.0)  # (110-100)*10
    assert t.commission == pytest.approx(2.1)  # entry 1.0 (full portion) + exit 1.1
    assert t.entry_order_id == str(entry.id)
    assert t.exit_order_id == str(exit_.id)


async def test_partial_reduce_emits_chunk_trade_and_keeps_remainder() -> None:
    b, _bus, trades = await _broker()
    await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    await b.submit_order(_order(OrderSide.SELL, qty=4, price=110.0))

    assert len(trades) == 1
    t = trades[0]
    assert t.quantity == 4.0
    assert t.pnl == pytest.approx(40.0)  # chunk delta (110-100)*4, not cumulative
    assert t.commission == pytest.approx(0.84)  # entry portion 0.4 + exit 0.44

    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 6.0


async def test_short_round_trip_direction_and_pnl() -> None:
    b, _bus, trades = await _broker()
    await b.submit_order(_order(OrderSide.SELL, qty=10, price=100.0))  # open short
    await b.submit_order(_order(OrderSide.BUY, qty=10, price=90.0))  # cover

    assert len(trades) == 1
    assert trades[0].direction == "SHORT"
    assert trades[0].pnl == pytest.approx(100.0)  # short: (100-90)*10


async def test_fill_notify_precedes_trade_notify_on_close() -> None:
    b, _bus, _trades = await _broker()
    sequence: list[tuple[str, str]] = []
    await b.subscribe_order_updates(
        lambda r: sequence.append(("fill", r.order_id)) if r.is_filled else None
    )
    # Re-subscribe trades into the same ordered log to observe interleaving.
    await b.unsubscribe_trades()
    await b.subscribe_trades(lambda t: sequence.append(("trade", t.exit_order_id or "")))

    await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    exit_ = _order(OrderSide.SELL, qty=10, price=110.0)
    await b.submit_order(exit_)

    fill_idx = sequence.index(("fill", str(exit_.id)))
    trade_idx = sequence.index(("trade", str(exit_.id)))
    assert fill_idx < trade_idx  # fill before trade for the closing order


async def test_synthetic_sl_exit_emits_trade() -> None:
    b, bus, trades = await _broker()
    b.set_current_price(_SYM, 100.0)
    await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0, sl=95.0))

    # Bar dips through the stop → synthetic SL exit fires and must emit a trade.
    await bus.publish(_bar(high=101.0, low=94.0, close=96.0))

    assert len(trades) == 1
    assert trades[0].exit_price == pytest.approx(95.0)  # filled at stop, slippage 0
    assert trades[0].direction == "LONG"


async def test_no_trade_on_open_only() -> None:
    b, _bus, trades = await _broker()
    result = await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    assert result.status == OrderStatus.FILLED
    assert trades == []  # opening a position emits no round-trip closure
