"""Contract-aware PnL through PaperBrokerAdapter.

A 0.25 move on 2 lots of XAUUSD is 50.00 USD, not 0.50: the broker's
``ContractSpec.multiplier`` (100 oz per lot) scales realized and unrealized PnL
into account currency, while the shipped margin accounting (cash moves only by
realized delta and commission) is untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.core.domain.trading import CommissionModel, PerContractCommissionModel
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

_T0 = datetime(2026, 9, 23, 14, 0, tzinfo=UTC)
_INITIAL = 100_000.0

XAUUSD_SYMBOL = "XAUUSD:EXNESS"
EURUSD_SYMBOL = "EURUSD:EXNESS"
# Exness lot grids: 100 oz of gold and 100 000 EUR per lot, sized in 0.01 lots.
XAUUSD = ContractSpec(multiplier=100.0, tick_size=0.001, lot_step=0.01)
EURUSD = ContractSpec(multiplier=100_000.0, tick_size=0.00001, lot_step=0.01)


def _order(symbol: str, side: OrderSide, *, qty: float, price: float) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="t",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        price=price,
    )


async def _broker(
    spec: ContractSpec, commission_model: CommissionModel | None = None
) -> tuple[PaperBrokerAdapter, EventBus, list[TradeClosedEvent]]:
    bus = EventBus()
    broker = PaperBrokerAdapter(
        initial_balance=_INITIAL,
        slippage_percent=0.0,
        fill_delay_ms=0,
        event_bus=bus,
        commission_model=commission_model,
        contract_spec=spec,
    )
    await broker.connect()
    trades: list[TradeClosedEvent] = []
    await broker.subscribe_trades(trades.append)
    return broker, bus, trades


async def _round_trip(
    spec: ContractSpec,
    symbol: str,
    *,
    qty: float,
    entry: float,
    exit_: float,
    commission_model: CommissionModel | None = None,
) -> tuple[PaperBrokerAdapter, list[TradeClosedEvent]]:
    broker, _, trades = await _broker(spec, commission_model)
    opened = await broker.submit_order(_order(symbol, OrderSide.BUY, qty=qty, price=entry))
    assert opened.status == OrderStatus.FILLED
    closed = await broker.submit_order(_order(symbol, OrderSide.SELL, qty=qty, price=exit_))
    assert closed.status == OrderStatus.FILLED
    return broker, trades


@pytest.mark.asyncio
async def test_xauusd_round_trip_realizes_50_usd() -> None:
    broker, trades = await _round_trip(XAUUSD, XAUUSD_SYMBOL, qty=2, entry=2650.00, exit_=2650.25)

    assert len(trades) == 1
    assert trades[0].pnl == pytest.approx(50.0, abs=1e-9)
    assert (await broker.get_balance()).available_balance == pytest.approx(_INITIAL + 50.0)


@pytest.mark.asyncio
async def test_xauusd_round_trip_with_per_contract_commission() -> None:
    broker, trades = await _round_trip(
        XAUUSD,
        XAUUSD_SYMBOL,
        qty=2,
        entry=2650.00,
        exit_=2650.25,
        commission_model=PerContractCommissionModel(2.5),
    )

    # 2 lots in + 2 lots out at 2.50 each.
    assert trades[0].pnl == pytest.approx(50.0, abs=1e-9)
    assert trades[0].commission == pytest.approx(10.0, abs=1e-9)
    balance = (await broker.get_balance()).available_balance
    assert balance == pytest.approx(_INITIAL + 50.0 - 10.0)


@pytest.mark.asyncio
async def test_eurusd_multiplier_100_000() -> None:
    _, trades = await _round_trip(EURUSD, EURUSD_SYMBOL, qty=1, entry=1.08000, exit_=1.08010)

    assert trades[0].pnl == pytest.approx(10.0, abs=1e-9)


@pytest.mark.asyncio
async def test_a_fractional_xauusd_lot_scales_by_the_contract_size() -> None:
    # 0.05 lot is 5 oz, so a 1.00 move is 5.00 USD.
    _, trades = await _round_trip(XAUUSD, XAUUSD_SYMBOL, qty=0.05, entry=2650.0, exit_=2651.0)

    assert trades[0].pnl == pytest.approx(5.0, abs=1e-9)


@pytest.mark.asyncio
async def test_linear_default_is_unchanged() -> None:
    # 0.5 BTC from 60_000 to 60_100 realizes 50.0 exactly as before contract specs.
    broker, trades = await _round_trip(
        LINEAR_SPEC, "BTCUSDT:BINANCE", qty=0.5, entry=60_000.0, exit_=60_100.0
    )

    assert trades[0].pnl == pytest.approx(50.0, abs=1e-9)
    assert (await broker.get_balance()).available_balance == pytest.approx(_INITIAL + 50.0)


@pytest.mark.asyncio
async def test_equity_curve_has_no_jump_at_fill_beyond_commission() -> None:
    symbol = XAUUSD_SYMBOL
    broker, bus, trades = await _broker(XAUUSD, PerContractCommissionModel(2.5))

    before_open = await broker.get_balance()
    await broker.submit_order(_order(symbol, OrderSide.BUY, qty=2, price=2650.00))
    after_open = await broker.get_balance()
    # Opening moves equity by the entry commission only.
    assert after_open.total_equity - before_open.total_equity == pytest.approx(-5.0)

    await bus.publish(
        BarCompletedEvent(
            symbol=symbol,
            interval="1m",
            bar_start=_T0,
            open=2650.00,
            high=2650.25,
            low=2650.00,
            close=2650.25,
            volume=100.0,
        )
    )
    marked = await broker.get_balance()
    # Mark-to-market is contract-scaled too, so closing at the mark cannot jump.
    assert marked.unrealized_pnl == pytest.approx(50.0)

    await broker.submit_order(_order(symbol, OrderSide.SELL, qty=2, price=2650.25))
    after_close = await broker.get_balance()

    trade = trades[0]
    exit_commission = trade.commission - 5.0
    assert after_close.available_balance - after_open.available_balance == pytest.approx(
        trade.pnl - exit_commission
    )
    assert after_close.total_equity - marked.total_equity == pytest.approx(-exit_commission)
