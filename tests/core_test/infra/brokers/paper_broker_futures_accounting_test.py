"""Tests pinning PaperBrokerAdapter futures/margin accounting (the correct model).

These tests assert the post-fix futures behavior and are written tests-first:
each one FAILS on the current spot-style code with a known arithmetic cause
(captured in the per-test ``current`` vs ``expected`` comments) and PASSES once
``_execute_fill`` stops debiting/crediting balance by notional and instead moves
cash only by realized-pnl delta, plus per-bar mark-to-market in
``_on_bar_completed``.

Accounting model (futures, 1x leverage, initial 10_000, no commission/slippage):
    total_equity      = balance + Σ unrealized_pnl(open)
    available_balance = balance
    open / add        : balance unchanged
    close / reduce    : balance += Δrealized (delta of THIS reduce, not cumulative)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import PositionSide
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"
_INITIAL = 10_000.0


def _order(
    side: OrderSide,
    *,
    qty: float,
    price: float,
    sl: float | None = None,
    tp: float | None = None,
) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="t",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
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


async def _broker(initial: float = _INITIAL) -> tuple[PaperBrokerAdapter, EventBus]:
    bus = EventBus()
    b = PaperBrokerAdapter(
        initial_balance=initial,
        slippage_percent=0.0,
        fill_delay_ms=0,
        event_bus=bus,
    )
    await b.connect()
    return b, bus


@pytest.mark.asyncio
async def test_long_round_trip_balance_only_changes_by_realized() -> None:
    # open 100@100 (futures: no debit) → mark 110 → close 100@110 (realized +1000).
    # current (spot, buggy): open debits 10000→0; close credits 11000 then adds
    #   cumulative realized 1000 → _balance = 12000 (double-count).
    # expected (futures): _balance = 10000 + 1000 = 11000.
    b, bus = await _broker()

    await b.submit_order(_order(OrderSide.BUY, qty=100, price=100.0))
    assert (await b.get_balance()).available_balance == pytest.approx(_INITIAL)

    await bus.publish(_bar(high=110.0, low=110.0, close=110.0))
    assert (await b.get_balance()).total_equity == pytest.approx(11_000.0)

    await b.submit_order(_order(OrderSide.SELL, qty=100, price=110.0))
    bal = await b.get_balance()
    assert bal.available_balance == pytest.approx(11_000.0)
    assert bal.total_equity == pytest.approx(11_000.0)
    assert (await b.get_positions()) == []


@pytest.mark.asyncio
async def test_open_all_in_total_equity_not_zero() -> None:
    # all-in open 100@100 with initial 10_000 (notional == balance).
    # current (spot): balance debited to 0, upl 0 → total_equity = 0 (the
    #   divide-by-zero seed in the equity curve).
    # expected (futures): total_equity == initial (upl 0 at entry, no mark yet).
    b, _ = await _broker()

    result = await b.submit_order(_order(OrderSide.BUY, qty=100, price=100.0))
    assert result.status == OrderStatus.FILLED

    bal = await b.get_balance()
    assert bal.total_equity == pytest.approx(_INITIAL)
    assert bal.unrealized_pnl == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_short_round_trip_balance() -> None:
    # open short 100@100 → mark 90 → cover 100@90 (realized +1000).
    # current (spot): open credits +10000→20000; cover debits 9000→11000 then
    #   adds cumulative realized 1000 → 12000 (double-count).
    # expected (futures): _balance = 11000.
    b, bus = await _broker()

    await b.submit_order(_order(OrderSide.SELL, qty=100, price=100.0))
    assert (await b.get_balance()).available_balance == pytest.approx(_INITIAL)

    await bus.publish(_bar(high=90.0, low=90.0, close=90.0))
    assert (await b.get_balance()).total_equity == pytest.approx(11_000.0)

    await b.submit_order(_order(OrderSide.BUY, qty=100, price=90.0))
    bal = await b.get_balance()
    assert bal.available_balance == pytest.approx(11_000.0)
    assert (await b.get_positions()) == []


@pytest.mark.asyncio
async def test_partial_close_no_double_count() -> None:
    # open 100@100 → close 40@110 (Δ+400) → close 60@110 (Δ+600).
    # current (spot): cumulative realized re-added each reduce → over-counts.
    # expected (futures): _balance = 10000 + (40+60)*10 = 11000; each reduce
    #   moves cash by its OWN delta, not the cumulative position.realized_pnl.
    b, _ = await _broker()

    await b.submit_order(_order(OrderSide.BUY, qty=100, price=100.0))
    await b.submit_order(_order(OrderSide.SELL, qty=40, price=110.0))
    assert (await b.get_balance()).available_balance == pytest.approx(10_400.0)

    await b.submit_order(_order(OrderSide.SELL, qty=60, price=110.0))
    assert (await b.get_balance()).available_balance == pytest.approx(11_000.0)
    assert (await b.get_positions()) == []


@pytest.mark.asyncio
async def test_add_then_reduce_long() -> None:
    # open 100@100, add 100@120 (avg entry 110, qty 200), reduce 100@130.
    # realized = (130 - 110) * 100 = 2000.
    # initial 100_000 so the add BUY's notional clears _can_afford (which gates
    # BUY notional against _balance, unchanged by this plan).
    # expected (futures): _balance = initial + 2000; remaining avg entry 110.
    initial = 100_000.0
    b, _ = await _broker(initial=initial)

    await b.submit_order(_order(OrderSide.BUY, qty=100, price=100.0))
    await b.submit_order(_order(OrderSide.BUY, qty=100, price=120.0))
    await b.submit_order(_order(OrderSide.SELL, qty=100, price=130.0))

    assert (await b.get_balance()).available_balance == pytest.approx(initial + 2_000.0)
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].side == PositionSide.LONG
    assert positions[0].entry_price == pytest.approx(110.0)
    assert positions[0].realized_pnl == pytest.approx(2_000.0)


@pytest.mark.asyncio
async def test_add_then_reduce_short() -> None:
    # open short 100@100, add 100@80 (avg entry 90, qty 200), cover 100@70.
    # realized = (90 - 70) * 100 = 2000.
    b, _ = await _broker()

    await b.submit_order(_order(OrderSide.SELL, qty=100, price=100.0))
    await b.submit_order(_order(OrderSide.SELL, qty=100, price=80.0))
    await b.submit_order(_order(OrderSide.BUY, qty=100, price=70.0))

    assert (await b.get_balance()).available_balance == pytest.approx(12_000.0)
    positions = await b.get_positions()
    assert len(positions) == 1
    assert positions[0].side == PositionSide.SHORT
    assert positions[0].entry_price == pytest.approx(90.0)
    assert positions[0].realized_pnl == pytest.approx(2_000.0)


@pytest.mark.asyncio
async def test_sl_tp_synthetic_exit_balance() -> None:
    # open long 100@100 SL=95; bar low 94 triggers SL exit at 95.
    # realized = (95 - 100) * 100 = -500.
    # current (spot): exit credits notional then adds realized → wrong balance.
    # expected (futures): _balance = initial - 500 = 9500; flat afterwards.
    b, bus = await _broker()

    await b.submit_order(_order(OrderSide.BUY, qty=100, price=100.0, sl=95.0))
    await bus.publish(_bar(high=99.0, low=94.0, close=96.0))

    assert (await b.get_positions()) == []
    bal = await b.get_balance()
    assert bal.total_equity == pytest.approx(9_500.0)
    assert bal.available_balance == pytest.approx(9_500.0)


@pytest.mark.asyncio
async def test_unrealized_tracks_price_per_bar() -> None:
    # open long 100@100 (no SL/TP), then a bar closes at 110.
    # current: position.current_price frozen at entry (bar only sets the broker's
    #   _current_prices dict) → unrealized 0 → total_equity flat at 10000.
    # expected: _on_bar_completed marks the open position to event.close → upl
    #   = (110-100)*100 = 1000 → total_equity = 11000.
    b, bus = await _broker()

    await b.submit_order(_order(OrderSide.BUY, qty=100, price=100.0))
    await bus.publish(_bar(high=111.0, low=109.0, close=110.0))

    bal = await b.get_balance()
    assert bal.unrealized_pnl == pytest.approx(1_000.0)
    assert bal.total_equity == pytest.approx(11_000.0)


@pytest.mark.asyncio
async def test_losing_short_cover_not_blocked_by_affordability() -> None:
    # short 100@100 (initial 10000), price rises to 150 → covering BUY notional
    # 15000 > balance. Under futures a cover consumes no margin, so it must fill,
    # not REJECT and strand the position. realized = (100-150)*100 = -5000.
    b, _ = await _broker()

    await b.submit_order(_order(OrderSide.SELL, qty=100, price=100.0))
    result = await b.submit_order(_order(OrderSide.BUY, qty=100, price=150.0))

    assert result.status == OrderStatus.FILLED
    assert (await b.get_positions()) == []
    assert (await b.get_balance()).available_balance == pytest.approx(5_000.0)


@pytest.mark.asyncio
async def test_available_balance_equals_balance_no_debit_on_open() -> None:
    # open 50@100 (notional 5000) with initial 10000.
    # current (spot): open debits → available = 5000.
    # expected (futures): open does NOT debit → available == balance == 10000
    #   and == total_equity at entry (upl 0). Pins available_balance = _balance.
    b, _ = await _broker()

    await b.submit_order(_order(OrderSide.BUY, qty=50, price=100.0))

    bal = await b.get_balance()
    assert bal.available_balance == pytest.approx(_INITIAL)
    assert bal.available_balance == pytest.approx(bal.total_equity)
