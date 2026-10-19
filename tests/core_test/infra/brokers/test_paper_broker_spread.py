"""Unit tests for the PaperBrokerAdapter constant spread: bars are bid prices and
ask = bid + spread, so BUY fills and SHORT SL/TP triggers use the ask side.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.symbol import LINEAR_SPEC
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_dispatch import _config_from_dict

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "XAUUSD:EXNESS"


def _order(side: OrderSide, *, sl: float | None = None, tp: float | None = None) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="t",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
        sl_price=sl,
        tp_price=tp,
    )


def _bar(*, high: float, low: float) -> BarCompletedEvent:
    return BarCompletedEvent(
        symbol=_SYM,
        interval="1m",
        bar_start=_T0,
        open=(high + low) / 2,
        high=high,
        low=low,
        close=(high + low) / 2,
        volume=1.0,
    )


async def _broker(spread: float) -> tuple[PaperBrokerAdapter, EventBus, list[OrderResult]]:
    bus = EventBus()
    b = PaperBrokerAdapter(
        initial_balance=1_000_000.0,
        slippage_percent=0.0,
        fill_delay_ms=0,
        event_bus=bus,
        spread=spread,
    )
    await b.connect()
    fills: list[OrderResult] = []
    await b.subscribe_order_updates(lambda r: fills.append(r))
    return b, bus, fills


@pytest.mark.parametrize(("spread", "expected"), [(0.4, 100.4), (0.0, 100.0)])
async def test_market_buy_fills_at_ask(spread: float, expected: float) -> None:
    b, _, _ = await _broker(spread)
    result = await b.submit_order(_order(OrderSide.BUY))
    assert result.filled_price == pytest.approx(expected)


@pytest.mark.parametrize("spread", [0.4, 0.0])
async def test_market_sell_fills_at_bid(spread: float) -> None:
    b, _, _ = await _broker(spread)
    result = await b.submit_order(_order(OrderSide.SELL))
    assert result.filled_price == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("spread", "high", "triggers"),
    [(0.4, 100.7, True), (0.4, 100.5, False), (0.0, 100.7, False), (0.0, 101.0, True)],
)
async def test_short_sl_triggers_on_ask_high(spread: float, high: float, triggers: bool) -> None:
    b, bus, fills = await _broker(spread)
    await b.submit_order(_order(OrderSide.SELL, sl=101.0))
    await bus.publish(_bar(high=high, low=99.5))
    exits = [f for f in fills if f.side == OrderSide.BUY]
    assert (await b.get_positions() == []) is triggers
    assert len(exits) == int(triggers)
    if triggers:
        assert exits[0].filled_price == pytest.approx(101.0)


@pytest.mark.parametrize(
    ("spread", "low", "triggers"),
    [(0.4, 98.7, False), (0.4, 98.5, True), (0.0, 99.2, False), (0.0, 98.7, True)],
)
async def test_short_tp_triggers_on_ask_low(spread: float, low: float, triggers: bool) -> None:
    b, bus, fills = await _broker(spread)
    await b.submit_order(_order(OrderSide.SELL, tp=99.0))
    await bus.publish(_bar(high=100.2, low=low))
    exits = [f for f in fills if f.side == OrderSide.BUY]
    assert (await b.get_positions() == []) is triggers
    assert len(exits) == int(triggers)
    if triggers:
        assert exits[0].filled_price == pytest.approx(99.0)


@pytest.mark.parametrize("spread", [0.4, 0.0])
async def test_long_sl_triggers_on_bid_low(spread: float) -> None:
    b, bus, fills = await _broker(spread)
    await b.submit_order(_order(OrderSide.BUY, sl=95.0))
    await bus.publish(_bar(high=100.0, low=94.9))
    exits = [f for f in fills if f.side == OrderSide.SELL]
    assert await b.get_positions() == []
    assert exits[0].filled_price == pytest.approx(95.0)


def test_config_from_dict_reads_spread() -> None:
    payload = {
        "strategy_code": "hitnrun2",
        "symbol": _SYM,
        "interval": "1m",
        "start_date": "2026-01-01T00:00:00+00:00",
        "end_date": "2026-01-02T00:00:00+00:00",
    }
    assert _config_from_dict({**payload, "spread": 0.4}, LINEAR_SPEC).spread == 0.4
    assert _config_from_dict(payload, LINEAR_SPEC).spread == 0.0
