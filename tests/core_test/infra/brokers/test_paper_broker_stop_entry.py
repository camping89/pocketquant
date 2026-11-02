from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.events import REASON_AUTO_SL, REASON_STRATEGY_EXIT
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = _T0 + timedelta(minutes=1)


@pytest.fixture(autouse=True)
def _sim_time() -> Iterator[None]:
    set_simulation_time(_T0)
    yield
    clear_simulation_time()


class _Broker:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.broker = PaperBrokerAdapter(
            initial_balance=1_000_000.0, slippage_percent=0.0, fill_delay_ms=0, event_bus=self.bus
        )
        self.results: list[OrderResult] = []
        self.trades: list[TradeClosedEvent] = []
        self.fills: list[OrderFilledEvent] = []
        self.bus.subscribe(OrderFilledEvent, lambda e: self.fills.append(e))

    def with_status(self, status: OrderStatus) -> list[OrderResult]:
        return [r for r in self.results if r.status is status]


async def _broker() -> _Broker:
    b = _Broker()
    await b.broker.connect()
    await b.broker.subscribe_order_updates(lambda r: b.results.append(r))
    await b.broker.subscribe_trades(lambda t: b.trades.append(t))
    return b


def _stop(
    side: OrderSide,
    stop: float,
    *,
    sl: float | None = None,
    tp: float | None = None,
    sid: str = "s1",
) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id=sid,
        symbol=_SYM,
        side=side,
        order_type=OrderType.STOP_MARKET,
        quantity=1.0,
        stop_price=stop,
        sl_price=sl,
        tp_price=tp,
    )


def _market(side: OrderSide, *, sl: float | None = None) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="s1",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
        sl_price=sl,
    )


# The bar of the pass: simulation time moves to it, as in a backtest replay.
def _bar(*, o: float, h: float, low: float, at: datetime = _T1) -> BarCompletedEvent:
    set_simulation_time(at)
    return BarCompletedEvent(
        symbol=_SYM,
        interval="1m",
        bar_start=at,
        open=o,
        high=h,
        low=low,
        close=o,
        volume=1.0,
        occurred_at=at,
    )


async def test_a_buy_stop_fills_on_a_later_bar_that_touches_it() -> None:
    b = await _broker()
    order = _stop(OrderSide.BUY, 101.0, sl=95.0)
    placed = await b.broker.submit_order(order)

    await b.broker.fill_resting_stops(_bar(o=100.0, h=101.5, low=99.5), {"s1"})

    assert placed.status is OrderStatus.SUBMITTED
    [filled] = b.with_status(OrderStatus.FILLED)
    assert filled.order_id == str(order.id)
    assert filled.filled_price == pytest.approx(101.0)
    assert filled.sl_price == 95.0
    assert len(await b.broker.get_positions()) == 1


async def test_a_buy_stop_gapped_over_fills_at_the_open() -> None:
    b = await _broker()
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))

    await b.broker.fill_resting_stops(_bar(o=102.0, h=103.0, low=101.5), {"s1"})

    [filled] = b.with_status(OrderStatus.FILLED)
    assert filled.filled_price == pytest.approx(102.0)


@pytest.mark.parametrize(("bar_open", "expected"), [(100.0, 99.0), (98.0, 98.0)])
async def test_a_sell_stop_fills_at_the_stop_or_the_open_below_it(
    bar_open: float, expected: float
) -> None:
    b = await _broker()
    await b.broker.submit_order(_stop(OrderSide.SELL, 99.0))

    await b.broker.fill_resting_stops(_bar(o=bar_open, h=100.5, low=97.5), {"s1"})

    [filled] = b.with_status(OrderStatus.FILLED)
    assert filled.filled_price == pytest.approx(expected)


async def test_a_stop_never_fills_on_the_bar_it_was_placed() -> None:
    b = await _broker()
    set_simulation_time(_T1)
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))

    await b.broker.fill_resting_stops(_bar(o=100.0, h=102.0, low=99.5), {"s1"})

    assert b.with_status(OrderStatus.FILLED) == []


async def test_a_cancelled_stop_never_fills() -> None:
    b = await _broker()
    placed = await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))

    assert await b.broker.cancel_order(placed.broker_order_id) is True
    # Not resting any more, so no fill can follow: still a successful cancel.
    assert await b.broker.cancel_order(placed.broker_order_id) is True
    await b.broker.fill_resting_stops(_bar(o=100.0, h=102.0, low=99.5), {"s1"})

    assert b.with_status(OrderStatus.FILLED) == []


async def test_a_stop_of_a_subscription_not_running_is_skipped() -> None:
    b = await _broker()
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))

    await b.broker.fill_resting_stops(_bar(o=100.0, h=102.0, low=99.5), set())

    assert b.with_status(OrderStatus.FILLED) == []
    assert b.with_status(OrderStatus.CANCELLED) == []
    assert len(b.broker._resting) == 1


async def test_a_stop_is_refused_while_the_subscription_holds_a_position() -> None:
    b = await _broker()
    await b.broker.submit_order(_market(OrderSide.BUY))
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))

    await b.broker.fill_resting_stops(_bar(o=100.0, h=102.0, low=99.5), {"s1"})

    [cancelled] = b.with_status(OrderStatus.CANCELLED)
    assert cancelled.error_message == "position open"
    assert b.broker._resting == {}
    assert len(b.with_status(OrderStatus.FILLED)) == 1


async def test_a_stop_fill_bar_checks_only_the_sl_against_that_bar() -> None:
    b = await _broker()
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0, sl=99.0, tp=103.0))

    await b.broker.fill_resting_stops(_bar(o=100.0, h=103.5, low=98.5), {"s1"})

    prices = [r.filled_price for r in b.with_status(OrderStatus.FILLED)]
    assert prices == [pytest.approx(101.0), pytest.approx(99.0)]
    assert [f.side for f in b.fills] == [OrderSide.SELL]
    assert await b.broker.get_positions() == []


async def test_a_stop_fill_bar_never_takes_the_tp() -> None:
    b = await _broker()
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0, sl=99.0, tp=103.0))

    await b.broker.fill_resting_stops(_bar(o=100.0, h=103.5, low=100.5), {"s1"})

    assert len(b.with_status(OrderStatus.FILLED)) == 1
    assert b.fills == []
    assert len(await b.broker.get_positions()) == 1


async def test_an_sl_already_past_the_fill_exits_at_the_fill() -> None:
    b = await _broker()
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0, sl=105.0))

    await b.broker.fill_resting_stops(_bar(o=100.0, h=101.5, low=99.5), {"s1"})

    [exit_fill] = b.fills
    assert exit_fill.filled_price == pytest.approx(101.0)


async def test_a_failing_subscriber_does_not_stop_the_other_fills() -> None:
    b = await _broker()
    first = _stop(OrderSide.BUY, 101.0, sid="s1")
    await b.broker.submit_order(first)
    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0, sid="s2"))

    def boom(result: OrderResult) -> None:
        if result.order_id == str(first.id):
            raise RuntimeError("mirror save failed")

    await b.broker.subscribe_order_updates(boom)

    with pytest.raises(RuntimeError):
        await b.broker.fill_resting_stops(_bar(o=100.0, h=101.5, low=99.5), {"s1", "s2"})

    assert len(b.with_status(OrderStatus.FILLED)) == 2


async def test_the_pass_takes_the_sl_of_an_open_position() -> None:
    b = await _broker()
    await b.broker.submit_order(_market(OrderSide.BUY, sl=99.0))
    event = _bar(o=100.0, h=100.5, low=98.0)

    await b.broker.fill_resting_stops(event, {"s1"})
    await b.broker._on_bar_completed(event)

    assert [(f.side, f.filled_price) for f in b.fills] == [(OrderSide.SELL, pytest.approx(99.0))]


async def test_close_position_fills_the_whole_position() -> None:
    b = await _broker()
    await b.broker.submit_order(_market(OrderSide.BUY))

    closed = await b.broker.close_position("s1", _SYM, reason=REASON_STRATEGY_EXIT)

    assert closed is True
    assert len(b.fills) == 1
    assert len(b.trades) == 1
    assert await b.broker.get_positions() == []
    assert await b.broker.close_position("s1", _SYM, reason=REASON_STRATEGY_EXIT) is False


async def test_an_exit_of_an_already_closed_position_does_nothing() -> None:
    b = await _broker()
    await b.broker.submit_order(_market(OrderSide.BUY))
    pos = b.broker._positions[f"s1:{_SYM}"]
    await b.broker.close_position("s1", _SYM, reason=REASON_STRATEGY_EXIT)

    again = await b.broker._fire_synthetic_exit(pos, 100.0, OrderSide.SELL, REASON_AUTO_SL)

    assert again is False
    assert await b.broker.get_positions() == []
    assert len(b.fills) == 1


async def test_drop_reset_and_restore_clear_resting_stops() -> None:
    b = await _broker()

    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))
    b.broker.drop_positions("s1")
    assert b.broker._resting == {}

    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))
    b.broker.reset()
    assert b.broker._resting == {}

    await b.broker.submit_order(_stop(OrderSide.BUY, 101.0))
    b.broker.restore([], 0.0)
    assert b.broker._resting == {}
