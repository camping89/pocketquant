"""Unit tests for EngulfingStrategy.

Synthetic OHLCV crafted per branch; direct ``on_bar_completed`` calls (no bus).
``on_order_filled`` is exercised directly to model the fill-driven open-direction
lifecycle: entry fill sets it, opposite fill clears it, a missing entry fill
(rejected/zero-size order) must NOT wedge the position cap.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.domain.risk.services.position_sizer_domain_service import (
    PositionSizerDomainService,
)
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.services.engulfing import EngulfingStrategy
from pocketquant.core.domain.strategy.value_objects import StrategyConfig

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"


def _bar(idx: int, o: float, h: float, lo: float, c: float) -> dict[str, Any]:
    return {
        "open": o,
        "high": h,
        "low": lo,
        "close": c,
        "volume": 1.0,
        "timestamp": _T0 + timedelta(minutes=idx),
        "symbol": _SYM,
        "interval": "1m",
    }


async def _strategy(
    direction: str = "both",
    lookback: int = 3,
    buf: float = 0.001,
    wick: float = 0.30,
) -> EngulfingStrategy:
    cfg = StrategyConfig(
        id="engulfing-test",
        name="Test",
        symbol=_SYM,
        interval="1m",
        parameters={
            "direction": direction,
            "key_level_lookback_bars": lookback,
            "sl_buffer_pct": buf,
            "max_rejection_wick_pct": wick,
        },
    )
    s = EngulfingStrategy(cfg)
    await s.on_start()
    return s


def _fill_order(side: OrderSide) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="engulfing-test",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
    )


# Strong bullish pattern (prev red, curr green engulfs body, tiny upper wick).
_PREV_RED = (100.0, 100.5, 97.5, 98.0)
_CURR_GREEN_STRONG = (97.0, 101.2, 96.8, 101.0)  # rejection ~0.045
_CURR_GREEN_WEAK = (97.0, 104.0, 96.8, 100.2)  # rejection ~0.528

# Strong bearish pattern (prev green, curr red engulfs body, tiny lower wick).
_PREV_GREEN = (98.0, 100.5, 97.5, 100.0)
_CURR_RED_STRONG = (101.0, 101.2, 96.8, 97.0)  # rejection ~0.045


async def _warm_to_pattern_long(
    s: EngulfingStrategy, *, filler_high: float = 100.0, filler_low: float = 99.0
) -> Any:
    """Feed 2 fillers + prev-red, then the strong-green pattern bar (idx 3)."""
    await s.on_bar_completed(_bar(0, 100.0, filler_high, filler_low, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, filler_high, filler_low, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_RED))
    return await s.on_bar_completed(_bar(3, *_CURR_GREEN_STRONG))


async def test_bullish_strong_emits_long_signal() -> None:
    s = await _strategy(direction="long")
    sig = await _warm_to_pattern_long(s)
    assert sig is not None
    assert sig.direction == Direction.LONG
    assert sig.entry_price == 101.0
    assert sig.entry_logic == "engulfing:bullish"


async def test_bullish_weak_rejected_by_quality_filter() -> None:
    s = await _strategy(direction="long", wick=0.30)
    await s.on_bar_completed(_bar(0, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_RED))
    sig = await s.on_bar_completed(_bar(3, *_CURR_GREEN_WEAK))
    assert sig is None


async def test_wick_filter_disabled_admits_weak_pattern() -> None:
    s = await _strategy(direction="long", wick=1.0)
    await s.on_bar_completed(_bar(0, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_RED))
    sig = await s.on_bar_completed(_bar(3, *_CURR_GREEN_WEAK))
    assert sig is not None
    assert sig.direction == Direction.LONG


async def test_long_sl_uses_pattern_low_minus_buffer() -> None:
    s = await _strategy(direction="long", buf=0.001)
    sig = await _warm_to_pattern_long(s)
    assert sig is not None
    pattern_low = min(_CURR_GREEN_STRONG[2], _PREV_RED[2])  # 96.8
    assert sig.stop_loss_price == pytest.approx(pattern_low * 0.999)
    # No same-bar stop-out: SL sits strictly below the entry bar's low.
    assert sig.stop_loss_price < _CURR_GREEN_STRONG[2]


async def test_long_tp_takes_rr_when_swing_near() -> None:
    s = await _strategy(direction="long")
    sig = await _warm_to_pattern_long(s, filler_high=100.0)  # window highs <= 100.5
    assert sig is not None
    entry, sl = 101.0, 96.8 * 0.999
    assert sig.take_profit_price == pytest.approx(entry + (entry - sl))


async def test_long_tp_takes_key_level_when_swing_far() -> None:
    s = await _strategy(direction="long")
    # A far prior swing high (110) in the lookback window outranks RR-based TP.
    sig = await _warm_to_pattern_long(s, filler_high=110.0)
    assert sig is not None
    assert sig.take_profit_price == pytest.approx(110.0)


async def test_key_level_window_excludes_current_bar_via_warmup_boundary() -> None:
    """Snapshot-before-append: first entry needs exactly ``lookback`` prior bars.

    With lookback=5 the same 4-bar sequence is one bar short of warmup, so the
    pattern at idx 3 must NOT fire — proving the window counts strictly-prior
    bars and never the current one.
    """
    s = await _strategy(direction="long", lookback=5)
    sig = await _warm_to_pattern_long(s)
    assert sig is None


async def test_short_strong_emits_short_signal_with_mirrored_sl_tp() -> None:
    s = await _strategy(direction="short")
    await s.on_bar_completed(_bar(0, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_GREEN))
    sig = await s.on_bar_completed(_bar(3, *_CURR_RED_STRONG))
    assert sig is not None
    assert sig.direction == Direction.SHORT
    entry = 97.0
    pattern_high = max(_CURR_RED_STRONG[1], _PREV_GREEN[1])  # 101.2
    sl = pattern_high * 1.001
    assert sig.stop_loss_price == pytest.approx(sl)
    assert sig.take_profit_price == pytest.approx(entry - (sl - entry))
    assert sig.take_profit_price < entry  # TP below entry for a short


async def test_direction_long_only_ignores_bearish() -> None:
    s = await _strategy(direction="long")
    await s.on_bar_completed(_bar(0, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_GREEN))
    assert await s.on_bar_completed(_bar(3, *_CURR_RED_STRONG)) is None


async def test_direction_short_only_ignores_bullish() -> None:
    s = await _strategy(direction="short")
    assert await _warm_to_pattern_long(s) is None


async def test_position_cap_blocks_second_entry_until_close() -> None:
    s = await _strategy(direction="long")
    first = await _warm_to_pattern_long(s)
    assert first is not None
    await s.on_order_filled(_fill_order(OrderSide.BUY), fill_price=101.0)
    assert s._open_direction == Direction.LONG
    # New engulfing while a position is open — blocked by the cap.
    await s.on_bar_completed(_bar(4, 101.0, 101.5, 99.0, 99.5))  # red, non-engulfing
    blocked = await s.on_bar_completed(_bar(5, 99.0, 102.0, 98.8, 101.5))  # green engulf
    assert blocked is None
    # Opposite-side fill closes the round trip → cap released, re-entry allowed.
    await s.on_order_filled(_fill_order(OrderSide.SELL), fill_price=101.5)
    assert s._open_direction is None
    await s.on_bar_completed(_bar(6, 101.0, 101.5, 99.0, 99.5))  # red prev
    reentry = await s.on_bar_completed(_bar(7, 99.0, 102.0, 98.8, 101.5))  # green engulf
    assert reentry is not None
    assert reentry.direction == Direction.LONG


async def test_unfilled_entry_does_not_wedge_open_direction() -> None:
    """No optimistic set: a signal with no entry fill leaves the cap open.

    Models a rejected / zero-size entry order — ``on_order_filled`` never fires
    for it, so the next valid pattern must still be allowed to signal.
    """
    s = await _strategy(direction="long")
    first = await _warm_to_pattern_long(s)
    assert first is not None
    assert s._open_direction is None  # not set in on_bar_completed
    await s.on_bar_completed(_bar(4, 101.0, 101.5, 99.0, 99.5))  # red prev, non-engulfing
    second = await s.on_bar_completed(_bar(5, 99.0, 102.0, 98.8, 101.5))  # green engulf
    assert second is not None
    assert second.direction == Direction.LONG


async def test_position_size_positive_for_shallow_pattern() -> None:
    s = await _strategy(direction="long", buf=0.001)
    sig = await _warm_to_pattern_long(s)
    assert sig is not None
    size = PositionSizerDomainService.calculate_size(
        account_balance=10_000.0,
        entry_price=sig.entry_price,  # type: ignore[arg-type]
        stop_loss_price=sig.stop_loss_price,
        risk_config=RiskConfig(),
    )
    assert size > 0


@pytest.mark.parametrize(
    "params",
    [
        {"direction": "weird"},
        {"max_rejection_wick_pct": 0.0},
        {"max_rejection_wick_pct": 1.5},
        {"key_level_lookback_bars": 0},
        {"sl_buffer_pct": -0.1},
    ],
)
def test_invalid_params_raise_value_error(params: dict) -> None:
    cfg = StrategyConfig(
        id="bad", name="bad", symbol=_SYM, interval="1m", parameters=params
    )
    with pytest.raises(ValueError):
        EngulfingStrategy(cfg)
