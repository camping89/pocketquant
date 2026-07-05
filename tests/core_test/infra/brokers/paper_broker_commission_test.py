"""PaperBrokerAdapter commission — debited on all four fill paths + _can_afford gate.

Model: futures, initial 10_000, slippage 0, commission 10 bps (0.001). Entry/exit
commission is |fill_price*qty|*bps/10000, debited from _balance at fill. Round-trip
net = gross_pnl − entry_commission − exit_commission. A broker with no injected
model (default bps=0) keeps pre-R3 balances (backward compat).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
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


async def _broker(
    *, initial: float = _INITIAL, bps: float = _BPS
) -> tuple[PaperBrokerAdapter, EventBus, list[OrderResult]]:
    bus = EventBus()
    b = PaperBrokerAdapter(
        initial_balance=initial,
        slippage_percent=0.0,
        fill_delay_ms=0,
        event_bus=bus,
        commission_model=PercentageCommissionModel(bps=bps),
    )
    fills: list[OrderResult] = []
    await b.subscribe_order_updates(lambda r: fills.append(r))
    await b.connect()
    return b, bus, fills


# --- Path 1: MARKET fill ------------------------------------------------------


async def test_market_entry_debits_commission() -> None:
    b, _bus, _fills = await _broker()
    result = await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    # commission = 100 * 10 * 0.001 = 1.0; open debits only commission (futures).
    assert result.commission == pytest.approx(1.0)
    assert (await b.get_balance()).available_balance == pytest.approx(_INITIAL - 1.0)


async def test_market_round_trip_net_is_gross_minus_both_commissions() -> None:
    b, _bus, _fills = await _broker()
    await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    exit_result = await b.submit_order(_order(OrderSide.SELL, qty=10, price=110.0))
    # gross = (110-100)*10 = 100; entry_comm = 1.0; exit_comm = 110*10*0.001 = 1.1.
    assert exit_result.commission == pytest.approx(1.1)
    assert (await b.get_balance()).available_balance == pytest.approx(
        _INITIAL + 100.0 - 1.0 - 1.1
    )


# --- Path 2: LIMIT immediate --------------------------------------------------


async def test_limit_immediate_debits_commission() -> None:
    b, _bus, _fills = await _broker()
    b.set_current_price(_SYM, 99.0)  # market below limit → BUY crosses immediately
    result = await b.submit_order(
        _order(OrderSide.BUY, qty=10, price=100.0, order_type=OrderType.LIMIT)
    )
    assert result.status == OrderStatus.FILLED
    assert result.commission == pytest.approx(1.0)
    assert (await b.get_balance()).available_balance == pytest.approx(_INITIAL - 1.0)


# --- Path 3: LIMIT cross on a future bar --------------------------------------


async def test_limit_cross_on_bar_debits_commission() -> None:
    b, bus, fills = await _broker()
    b.set_current_price(_SYM, 105.0)  # above limit → no immediate cross, goes pending
    submit = await b.submit_order(
        _order(OrderSide.BUY, qty=10, price=100.0, order_type=OrderType.LIMIT)
    )
    assert submit.status == OrderStatus.SUBMITTED
    await bus.publish(_bar(high=106.0, low=99.0, close=101.0))  # low crosses 100
    filled = [f for f in fills if f.status == OrderStatus.FILLED]
    assert len(filled) == 1
    assert filled[0].commission == pytest.approx(1.0)
    assert (await b.get_balance()).available_balance == pytest.approx(_INITIAL - 1.0)


# --- Path 4: synthetic SL/TP exit (risk #1 — the easy path to miss) -----------


async def test_synthetic_tp_exit_debits_commission() -> None:
    b, bus, fills = await _broker()
    await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0, tp=110.0))
    await bus.publish(_bar(high=111.0, low=100.0, close=110.0))  # high hits TP
    exit_fills = [f for f in fills if f.side == OrderSide.SELL and f.status == OrderStatus.FILLED]
    assert len(exit_fills) == 1
    # exit fill at TP 110 → commission 110*10*0.001 = 1.1.
    assert exit_fills[0].commission == pytest.approx(1.1)
    # balance = initial - entry_comm(1.0) + gross(100) - exit_comm(1.1).
    assert (await b.get_balance()).available_balance == pytest.approx(
        _INITIAL + 100.0 - 1.0 - 1.1
    )
    assert (await b.get_positions()) == []


# --- _can_afford gate includes commission -------------------------------------


async def test_can_afford_rejects_when_commission_tips_over_balance() -> None:
    b, _bus, _fills = await _broker(initial=1_000.0)
    # notional 10*100 = 1000 == balance; commission 1.0 tips it over → REJECTED.
    result = await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    assert result.status == OrderStatus.REJECTED
    assert (await b.get_balance()).available_balance == pytest.approx(1_000.0)


# --- Backward compat: no model → bps=0 → pre-R3 balances ----------------------


async def test_default_model_bps_zero_keeps_pre_r3_balance() -> None:
    bus = EventBus()
    b = PaperBrokerAdapter(
        initial_balance=_INITIAL, slippage_percent=0.0, fill_delay_ms=0, event_bus=bus
    )
    await b.connect()
    result = await b.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    assert result.commission == 0.0
    assert (await b.get_balance()).available_balance == pytest.approx(_INITIAL)


# --- Factory wiring: Settings fraction → model bps (no ×10000 unit bug) --------


async def test_broker_factory_percent_to_bps() -> None:
    from pocketquant.app.di.broker_factory import BrokerFactory

    factory = BrokerFactory(EventBus())
    broker = factory.create(
        "paper",
        {"initial_balance": _INITIAL, "slippage_percent": 0.0, "commission_percent": 0.0004},
    )
    assert isinstance(broker, PaperBrokerAdapter)
    await broker.connect()
    result = await broker.submit_order(_order(OrderSide.BUY, qty=10, price=100.0))
    # 0.0004 fraction → 4 bps → 100*10*0.0004 = 0.4.
    assert result.commission == pytest.approx(0.4)
