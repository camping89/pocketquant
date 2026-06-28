"""Unit tests for HitNRun2Strategy.

Synthetic OHLCV is crafted so each test exercises a single rule branch.
Direct ``on_bar_completed`` calls — no EventBus / broker plumbing needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.services.hitnrun2 import HitNRun2Strategy
from pocketquant.core.domain.strategy.value_objects import StrategyConfig

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(
    idx: int,
    *,
    h: float | None = None,
    lo: float | None = None,
    c: float | None = None,
    base: float = 100.0,
) -> dict[str, Any]:
    return {
        "high": h if h is not None else base + 0.5,
        "low": lo if lo is not None else base - 0.5,
        "close": c if c is not None else base,
        "open": base,
        "volume": 1.0,
        "timestamp": _T0 + timedelta(minutes=idx),
        "symbol": "BTCUSDT:BINANCE",
        "interval": "1m",
    }


async def _strategy(
    direction: str = "both",
    entry: int = 5,
    sl: int = 8,
    tp: int = 3,
    max_loss: float = 0.01,
    min_profit: float = 0.02,
) -> HitNRun2Strategy:
    cfg = StrategyConfig(
        id="hitnrun2-test",
        name="Test",
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        parameters={
            "entry_lookback_bars": entry,
            "sl_lookback_bars": sl,
            "tp_lookback_bars": tp,
            "max_loss_pct": max_loss,
            "min_profit_pct": min_profit,
            "direction": direction,
        },
    )
    s = HitNRun2Strategy(cfg)
    await s.on_start()
    return s


def _exit_order(side: OrderSide) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="hitnrun2-test",
        symbol="BTCUSDT:BINANCE",
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
    )


async def test_warmup_returns_none_until_sl_lookback_full() -> None:
    s = await _strategy(sl=8)
    for i in range(7):
        assert await s.on_bar_completed(_bar(i)) is None


async def test_long_entry_on_breakdown_below_prev_window_low() -> None:
    s = await _strategy(direction="long", entry=5, sl=8, tp=3)
    # 8 warmup bars at base=100 -> lows=99.5
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    # Trigger bar: close 99.0 breaks below min(prev_lows[-5:]) = 99.5
    sig = await s.on_bar_completed(_bar(8, h=99.5, lo=98.5, c=99.0, base=99.0))
    assert sig is not None
    assert sig.direction == Direction.LONG
    assert sig.entry_price == 99.0


async def test_short_entry_on_breakup_above_prev_window_high() -> None:
    s = await _strategy(direction="short", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    sig = await s.on_bar_completed(_bar(8, h=101.5, lo=100.5, c=101.0, base=101.0))
    assert sig is not None
    assert sig.direction == Direction.SHORT
    assert sig.entry_price == 101.0


async def test_sl_capped_at_max_loss_pct_when_window_low_too_far() -> None:
    """Window-min low = 50, entry=99 -> raw SL = 50, cap = 99*(1-0.01)=98.01 -> SL = 98.01."""
    s = await _strategy(direction="long", entry=5, sl=8, tp=3, max_loss=0.01)
    # 8 warmup bars: first has low=50 (extreme), rest at 99.5
    await s.on_bar_completed(_bar(0, h=51, lo=50, c=50.5, base=50.5))
    for i in range(1, 8):
        await s.on_bar_completed(_bar(i))
    sig = await s.on_bar_completed(_bar(8, h=99.5, lo=98.5, c=99.0, base=99.0))
    assert sig is not None
    assert sig.stop_loss_price == pytest.approx(99.0 * 0.99)


async def test_sl_uses_technical_when_within_cap() -> None:
    """Window-min low = 98.5 within 1% cap (97.02) -> SL = 98.5."""
    s = await _strategy(direction="long", entry=5, sl=8, tp=3, max_loss=0.02)
    await s.on_bar_completed(_bar(0, h=99.0, lo=98.5, c=98.7, base=98.7))
    for i in range(1, 8):
        await s.on_bar_completed(_bar(i, base=99.0))
    sig = await s.on_bar_completed(_bar(8, h=99.0, lo=97.5, c=98.0, base=98.0))
    assert sig is not None
    # min(prev_lows_sl) = 98.5 ; cap = 98 * 0.98 = 96.04 -> max = 98.5
    assert sig.stop_loss_price == pytest.approx(98.5)


async def test_tp_uses_min_profit_pct_when_window_high_too_close() -> None:
    """Window-max high = 100.5, entry=99 -> raw TP=100.5, cap=99*1.02=100.98 -> TP=100.98."""
    s = await _strategy(direction="long", entry=5, sl=8, tp=3, min_profit=0.02)
    for i in range(8):
        await s.on_bar_completed(_bar(i, h=100.5, lo=99.5, c=100.0, base=100.0))
    sig = await s.on_bar_completed(_bar(8, h=100.0, lo=98.5, c=99.0, base=99.0))
    assert sig is not None
    assert sig.take_profit_price == pytest.approx(99.0 * 1.02)


async def test_tp_uses_technical_when_above_min_target() -> None:
    """Window-max high = 105 (within last 3 bars), entry=99 -> TP=105 (above cap 100.98)."""
    s = await _strategy(direction="long", entry=5, sl=8, tp=3, min_profit=0.02)
    # First 7 bars at base=100 ; bar idx=7 spikes high=105 so prev_highs_tp[-3:] includes 105.
    for i in range(7):
        await s.on_bar_completed(_bar(i, h=100.5, lo=99.5, c=100.0, base=100.0))
    await s.on_bar_completed(_bar(7, h=105.0, lo=99.5, c=100.0, base=100.0))
    sig = await s.on_bar_completed(_bar(8, h=100.0, lo=98.5, c=99.0, base=99.0))
    assert sig is not None
    assert sig.take_profit_price == pytest.approx(105.0)


async def test_direction_long_only_skips_short_signal() -> None:
    s = await _strategy(direction="long", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    # Breakup bar — should be ignored under direction=long.
    assert await s.on_bar_completed(_bar(8, h=101.5, lo=100.5, c=101.0, base=101.0)) is None


async def test_direction_short_only_skips_long_signal() -> None:
    s = await _strategy(direction="short", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    assert await s.on_bar_completed(_bar(8, h=99.5, lo=98.5, c=99.0, base=99.0)) is None


async def test_position_cap_blocks_second_signal_while_open() -> None:
    s = await _strategy(direction="long", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    first = await s.on_bar_completed(_bar(8, h=99.5, lo=98.5, c=99.0, base=99.0))
    assert first is not None
    # Next breakdown bar — must be ignored because position is open.
    second = await s.on_bar_completed(_bar(9, h=98.5, lo=97.0, c=97.5, base=97.5))
    assert second is None


async def test_on_fill_long_close_resets_state_for_next_entry() -> None:
    s = await _strategy(direction="long", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    await s.on_bar_completed(_bar(8, h=99.5, lo=98.5, c=99.0, base=99.0))
    await s.on_order_filled(_exit_order(OrderSide.SELL), fill_price=98.5)
    assert s._open_direction is None
    # Next breakdown bar — can enter again.
    sig = await s.on_bar_completed(_bar(9, h=98.5, lo=97.0, c=97.5, base=97.5))
    assert sig is not None and sig.direction == Direction.LONG


async def test_on_fill_short_close_resets_state() -> None:
    s = await _strategy(direction="short", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    await s.on_bar_completed(_bar(8, h=101.5, lo=100.5, c=101.0, base=101.0))
    await s.on_order_filled(_exit_order(OrderSide.BUY), fill_price=101.5)
    assert s._open_direction is None


async def test_on_fill_same_side_does_not_reset() -> None:
    """A BUY-side fill while LONG (scale-in) must NOT reset _open_direction."""
    s = await _strategy(direction="long", entry=5, sl=8, tp=3)
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    await s.on_bar_completed(_bar(8, h=99.5, lo=98.5, c=99.0, base=99.0))
    await s.on_order_filled(_exit_order(OrderSide.BUY), fill_price=99.0)
    assert s._open_direction == Direction.LONG


async def test_current_bar_low_excluded_from_prev_window() -> None:
    """Current bar must not contribute to prev-window snapshot."""
    s = await _strategy(direction="long", entry=5, sl=8, tp=3)
    # 8 warm bars at 100 +/- 0.5 -> prev_lows = 99.5
    for i in range(8):
        await s.on_bar_completed(_bar(i))
    # 9th bar low=98 dips below 99.5; close above prev_low_4h(99.5) -> no signal.
    sig = await s.on_bar_completed(_bar(8, h=100.0, lo=98.0, c=99.6, base=99.6))
    assert sig is None  # close (99.6) is NOT below min(prev_lows_entry)=99.5
    # 10th bar: window now includes idx8 low=98 -> prev_low_4h=98.
    # Close 97.5 < 98 -> signal.
    sig2 = await s.on_bar_completed(_bar(9, h=98.5, lo=97.0, c=97.5, base=97.5))
    assert sig2 is not None
    assert sig2.direction == Direction.LONG


async def test_invalid_direction_raises() -> None:
    cfg = StrategyConfig(
        id="bad",
        name="bad",
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        parameters={"direction": "weird"},
    )
    with pytest.raises(ValueError, match="direction"):
        HitNRun2Strategy(cfg)
