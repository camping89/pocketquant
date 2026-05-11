"""Unit tests for FIFO LotTracker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pocketquant.backtest.engine.lot_tracker import LotTracker


@pytest.fixture
def base_time() -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC)


def _feed(
    tracker: LotTracker,
    side: str,
    qty: float,
    price: float,
    time: datetime,
    commission: float = 0.0,
    sl: float | None = None,
    tp: float | None = None,
):
    return tracker.feed(
        side=side,  # type: ignore[arg-type]
        qty=qty,
        price=price,
        time=time,
        order_id=f"o-{side}-{qty}-{price}",
        commission=commission,
        sl_price=sl,
        tp_price=tp,
    )


# --- Opening ----------------------------------------------------------------


def test_open_single_long_lot(base_time: datetime) -> None:
    tracker = LotTracker()
    outcome = _feed(tracker, "LONG", 1.0, 100.0, base_time, commission=0.1)
    assert outcome.opened is not None
    assert outcome.opened.direction == "LONG"
    assert outcome.opened.qty_remaining == 1.0
    assert outcome.opened.entry_commission == pytest.approx(0.1)
    assert outcome.consumed == []
    assert tracker.has_long_lot()
    assert not tracker.has_short_lot()
    assert tracker.net_qty() == pytest.approx(1.0)


def test_open_single_short_lot(base_time: datetime) -> None:
    tracker = LotTracker()
    outcome = _feed(tracker, "SHORT", 2.0, 50.0, base_time)
    assert outcome.opened is not None
    assert outcome.opened.direction == "SHORT"
    assert tracker.has_short_lot()
    assert tracker.net_qty() == pytest.approx(-2.0)


def test_zero_qty_is_noop(base_time: datetime) -> None:
    tracker = LotTracker()
    outcome = _feed(tracker, "LONG", 0.0, 100.0, base_time)
    assert outcome.opened is None
    assert outcome.consumed == []
    assert tracker.lots == []


# --- FIFO consume -----------------------------------------------------------


def test_close_full_long_round_trip(base_time: datetime) -> None:
    tracker = LotTracker()
    _feed(tracker, "LONG", 1.0, 100.0, base_time, commission=0.1)
    outcome = _feed(
        tracker, "SHORT", 1.0, 110.0, base_time + timedelta(hours=1), commission=0.11
    )
    assert outcome.opened is None
    assert len(outcome.consumed) == 1
    c = outcome.consumed[0]
    assert c.qty_closed == pytest.approx(1.0)
    assert c.lot.direction == "LONG"
    assert c.entry_commission_portion == pytest.approx(0.1)
    assert c.exit_commission_portion == pytest.approx(0.11)
    assert tracker.net_qty() == 0.0


def test_close_full_short_round_trip(base_time: datetime) -> None:
    tracker = LotTracker()
    _feed(tracker, "SHORT", 1.0, 100.0, base_time)
    outcome = _feed(tracker, "LONG", 1.0, 90.0, base_time + timedelta(hours=1))
    assert outcome.opened is None
    assert len(outcome.consumed) == 1
    assert outcome.consumed[0].lot.direction == "SHORT"
    assert tracker.net_qty() == 0.0


def test_fifo_two_lots_one_close(base_time: datetime) -> None:
    """Two BUYs at different prices, one SELL takes both — FIFO order."""
    tracker = LotTracker()
    _feed(tracker, "LONG", 1.0, 100.0, base_time)
    _feed(tracker, "LONG", 1.0, 110.0, base_time + timedelta(minutes=1))
    outcome = _feed(tracker, "SHORT", 2.0, 120.0, base_time + timedelta(hours=1))
    assert len(outcome.consumed) == 2
    # First consumed should be the first opened (FIFO)
    assert outcome.consumed[0].lot.entry_price == pytest.approx(100.0)
    assert outcome.consumed[1].lot.entry_price == pytest.approx(110.0)
    assert tracker.net_qty() == 0.0


def test_partial_close_keeps_remaining(base_time: datetime) -> None:
    """1 BUY qty=10 → 1 SELL qty=4 → lot left with qty=6."""
    tracker = LotTracker()
    _feed(tracker, "LONG", 10.0, 100.0, base_time, commission=1.0)
    outcome = _feed(tracker, "SHORT", 4.0, 110.0, base_time + timedelta(hours=1), commission=0.44)
    assert len(outcome.consumed) == 1
    assert outcome.consumed[0].qty_closed == pytest.approx(4.0)
    # Entry commission proportionally allocated (4/10)
    assert outcome.consumed[0].entry_commission_portion == pytest.approx(0.4)
    # Exit commission proportional to closed qty out of 4 sold (=full)
    assert outcome.consumed[0].exit_commission_portion == pytest.approx(0.44)
    assert outcome.opened is None
    assert tracker.net_qty() == pytest.approx(6.0)
    remaining = tracker.lots[0]
    assert remaining.qty_remaining == pytest.approx(6.0)
    # Entry commission on the lot stays at original (we report portion via consumed)
    assert remaining.entry_commission == pytest.approx(1.0)


# --- Flip -------------------------------------------------------------------


def test_flip_long_to_short(base_time: datetime) -> None:
    """LONG 10 → SELL 15 closes all LONG and opens SHORT 5."""
    tracker = LotTracker()
    _feed(tracker, "LONG", 10.0, 100.0, base_time, commission=1.0)
    outcome = _feed(
        tracker, "SHORT", 15.0, 90.0, base_time + timedelta(hours=1), commission=1.35
    )
    assert len(outcome.consumed) == 1
    assert outcome.consumed[0].qty_closed == pytest.approx(10.0)
    # Exit commission proportional to closed portion of sell qty (10/15)
    assert outcome.consumed[0].exit_commission_portion == pytest.approx(1.35 * 10 / 15)
    assert outcome.opened is not None
    assert outcome.opened.direction == "SHORT"
    assert outcome.opened.qty_remaining == pytest.approx(5.0)
    assert outcome.opened.entry_commission == pytest.approx(1.35 * 5 / 15)
    assert tracker.net_qty() == pytest.approx(-5.0)


def test_flip_short_to_long(base_time: datetime) -> None:
    tracker = LotTracker()
    _feed(tracker, "SHORT", 5.0, 100.0, base_time)
    outcome = _feed(tracker, "LONG", 8.0, 90.0, base_time + timedelta(hours=1))
    assert len(outcome.consumed) == 1
    assert outcome.consumed[0].qty_closed == pytest.approx(5.0)
    assert outcome.opened is not None
    assert outcome.opened.direction == "LONG"
    assert outcome.opened.qty_remaining == pytest.approx(3.0)


def test_flip_consumes_multiple_lots(base_time: datetime) -> None:
    """LONG 3 + LONG 4 → SELL 10 → 2 closes + open SHORT 3."""
    tracker = LotTracker()
    _feed(tracker, "LONG", 3.0, 100.0, base_time)
    _feed(tracker, "LONG", 4.0, 105.0, base_time + timedelta(minutes=1))
    outcome = _feed(tracker, "SHORT", 10.0, 95.0, base_time + timedelta(hours=1))
    assert len(outcome.consumed) == 2
    assert outcome.consumed[0].qty_closed == pytest.approx(3.0)
    assert outcome.consumed[1].qty_closed == pytest.approx(4.0)
    assert outcome.opened is not None
    assert outcome.opened.direction == "SHORT"
    assert outcome.opened.qty_remaining == pytest.approx(3.0)


# --- Scale in/out -----------------------------------------------------------


def test_scale_out_two_partial_sells(base_time: datetime) -> None:
    """1 BUY qty=10 → 2 SELL (4+6) → fully closes lot, no SHORT opened."""
    tracker = LotTracker()
    _feed(tracker, "LONG", 10.0, 100.0, base_time, commission=1.0)
    out1 = _feed(tracker, "SHORT", 4.0, 110.0, base_time + timedelta(hours=1))
    out2 = _feed(tracker, "SHORT", 6.0, 120.0, base_time + timedelta(hours=2))
    assert len(out1.consumed) == 1 and out1.consumed[0].qty_closed == pytest.approx(4.0)
    assert len(out2.consumed) == 1 and out2.consumed[0].qty_closed == pytest.approx(6.0)
    assert out2.opened is None
    assert tracker.net_qty() == 0.0
    assert tracker.lots == []
