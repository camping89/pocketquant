"""PositionAggregate emits TradeClosedEvent on reduce/close (average-cost).

Covers economic payload correctness: chunk pnl (non-cumulative), commission
portion draining, duration, direction as PositionSide.name, and sim-time inject.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.position.events import TradeClosedEvent


def _only_trade_event(position: PositionAggregate) -> TradeClosedEvent:
    trades = [e for e in position.collect_events() if isinstance(e, TradeClosedEvent)]
    assert len(trades) == 1
    return trades[0]


def test_full_close_emits_trade_event_with_pnl_commission_duration_direction() -> None:
    opened = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    exited = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
    position = PositionAggregate.open(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=2.0,
        entry_order_id="entry-1",
        entry_commission=4.0,
        opened_at=opened,
    )

    position.reduce_quantity(
        2.0, 110.0, exit_commission=1.0, exit_order_id="exit-1", exit_time=exited
    )

    trade = _only_trade_event(position)
    assert trade.direction == "LONG"
    assert trade.entry_order_id == "entry-1"
    assert trade.exit_order_id == "exit-1"
    assert trade.entry_price == 100.0
    assert trade.exit_price == 110.0
    assert trade.quantity == 2.0
    assert trade.pnl == 20.0  # (110-100) * 2
    assert trade.commission == 5.0  # full entry portion (4.0) + exit (1.0)
    assert trade.entry_time == opened
    assert trade.exit_time == exited
    assert trade.duration_seconds == 3600.0
    assert position.is_closed


def test_partial_reduce_avg_cost_pnl_and_commission_portion() -> None:
    position = PositionAggregate.open(
        subscription_id="sub-1",
        symbol="ETHUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=2.0,
        entry_commission=4.0,
    )
    # Scale in: avg entry = (100*2 + 200*2)/4 = 150; commission accrues to 4+2=6.
    position.add_quantity(2.0, 200.0, commission=2.0)
    position.collect_events()  # drain open + update events

    # Reduce 1 of 4 held → chunk pnl vs avg cost 150, portion = 6 * 1/4 = 1.5.
    position.reduce_quantity(1.0, 300.0, exit_commission=0.5)

    trade = _only_trade_event(position)
    assert trade.entry_price == 150.0
    assert trade.quantity == 1.0
    assert trade.pnl == 150.0  # (300 - 150) * 1  (chunk delta, not cumulative)
    assert trade.commission == 2.0  # portion 1.5 + exit 0.5
    assert position.quantity == 3.0
    assert position.entry_commission == 4.5  # 6.0 - 1.5 drained
    assert not position.is_closed


def test_short_direction_and_sim_time_opened_at_inject() -> None:
    opened = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    exited = datetime(2026, 3, 1, 12, 30, 0, tzinfo=UTC)
    position = PositionAggregate.open(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.SHORT,
        entry_price=100.0,
        quantity=1.0,
        opened_at=opened,
    )
    assert position.opened_at == opened  # sim-time injected, not wall-clock

    position.reduce_quantity(1.0, 90.0, exit_time=exited)

    trade = _only_trade_event(position)
    assert trade.direction == "SHORT"  # PositionSide.name, not .value ("short")
    assert trade.pnl == 10.0  # short: (100 - 90) * 1
    assert trade.duration_seconds == 1800.0


def test_opened_at_defaults_to_wall_clock_when_not_injected() -> None:
    position = PositionAggregate.open(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=1.0,
    )
    assert position.opened_at.tzinfo is not None  # utc_now default_factory fired


def test_reduce_without_new_args_stays_backward_compatible() -> None:
    position = PositionAggregate.open(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=1.0,
    )
    position.collect_events()

    position.reduce_quantity(1.0, 110.0)  # legacy 2-arg call still emits a trade

    trade = _only_trade_event(position)
    assert trade.pnl == 10.0
    assert trade.commission == 0.0  # no commission supplied → zero
    assert trade.entry_order_id is None
