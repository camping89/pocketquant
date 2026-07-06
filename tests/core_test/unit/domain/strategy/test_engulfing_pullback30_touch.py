"""Unit tests for EngulfingPullback30TouchStrategyService.

Two-bar state machine: the engulfing bar arms (never signals); the next bar
resolves — enter-on-touch, discard-on-miss, or skip-on-SL-breach. Direct
``on_bar_completed`` calls (no bus); OHLCV crafted per branch with level/SL
computed by hand and asserted via ``pytest.approx``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.services.engulfing_pullback30_touch_strategy_service import (
    EngulfingPullback30TouchStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import StrategyConfig

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SYM = "BTCUSDT:BINANCE"

# Strong bullish pattern (prev red, curr green engulfs body, tiny upper wick).
_PREV_RED = (100.0, 100.5, 97.5, 98.0)
_CURR_GREEN_STRONG = (97.0, 101.2, 96.8, 101.0)  # rejection ~0.045

# Strong bearish pattern (prev green, curr red engulfs body, tiny lower wick).
_PREV_GREEN = (98.0, 100.5, 97.5, 100.0)
_CURR_RED_STRONG = (101.0, 101.2, 96.8, 97.0)  # rejection ~0.045

_PULLBACK = 0.30
_BUF = 0.001

# LONG arm math from _CURR_GREEN_STRONG over _PREV_RED (pullback_pct=0.30).
_LONG_LEVEL = 101.0 - _PULLBACK * (101.0 - 97.0)  # 99.8
_LONG_SL = min(96.8, 97.5) * (1 - _BUF)  # 96.7032

# SHORT arm math from _CURR_RED_STRONG over _PREV_GREEN.
_SHORT_LEVEL = 97.0 + _PULLBACK * (101.0 - 97.0)  # 98.2
_SHORT_SL = max(101.2, 100.5) * (1 + _BUF)  # 101.3012

# Next-bar (N+1) resolve fixtures — (open, high, low, close).
_TOUCH_LONG = (100.5, 100.8, 99.5, 100.2)  # low 99.5 <= 99.8, low > SL, entry 100.2
_NOTOUCH_LONG = (100.5, 100.8, 100.0, 100.5)  # low 100.0 > 99.8
_SLHIT_LONG = (100.5, 100.8, 96.0, 100.2)  # low 96.0 <= SL 96.7032
_TOUCH_SHORT = (97.0, 98.5, 96.5, 97.5)  # high 98.5 >= 98.2, high < SL, entry 97.5


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
    buf: float = _BUF,
    wick: float = 0.30,
    pullback: float = _PULLBACK,
) -> EngulfingPullback30TouchStrategyService:
    cfg = StrategyConfig(
        id="engulfing-pb30-test",
        name="Test",
        symbol=_SYM,
        interval="1m",
        parameters={
            "direction": direction,
            "key_level_lookback_bars": lookback,
            "sl_buffer_pct": buf,
            "max_rejection_wick_pct": wick,
            "pullback_pct": pullback,
        },
    )
    s = EngulfingPullback30TouchStrategyService(cfg)
    await s.on_start()
    return s


def _fill_order(side: OrderSide) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="engulfing-pb30-test",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
    )


async def _arm_long(
    s: EngulfingPullback30TouchStrategyService,
    *,
    filler_high: float = 100.0,
    filler_low: float = 99.0,
) -> Any:
    """Feed 2 fillers + prev-red, then the strong-green pattern bar (idx 3).

    Returns the pattern-bar result (must be None — armed, not signalled).
    """
    await s.on_bar_completed(_bar(0, 100.0, filler_high, filler_low, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, filler_high, filler_low, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_RED))
    return await s.on_bar_completed(_bar(3, *_CURR_GREEN_STRONG))


async def _arm_short(s: EngulfingPullback30TouchStrategyService) -> Any:
    await s.on_bar_completed(_bar(0, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(1, 100.0, 100.0, 99.0, 100.0))
    await s.on_bar_completed(_bar(2, *_PREV_GREEN))
    return await s.on_bar_completed(_bar(3, *_CURR_RED_STRONG))


async def test_engulfing_bar_does_not_emit_signal() -> None:
    s = await _strategy(direction="long")
    armed = await _arm_long(s)
    assert armed is None
    assert s._armed is not None
    assert s._armed["direction"] == Direction.LONG
    assert s._armed["level"] == pytest.approx(_LONG_LEVEL)


async def test_next_bar_touch_emits_long_at_next_close() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s)
    sig = await s.on_bar_completed(_bar(4, *_TOUCH_LONG))
    assert sig is not None
    assert sig.direction == Direction.LONG
    assert sig.entry_price == pytest.approx(_TOUCH_LONG[3])  # close(N+1) == 100.2
    assert sig.entry_logic == "engulfing_pullback30_touch:bullish"
    assert s._armed is None


async def test_next_bar_no_touch_discards_setup() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s)
    miss = await s.on_bar_completed(_bar(4, *_NOTOUCH_LONG))
    assert miss is None
    assert s._armed is None
    # A subsequent non-engulfing bar stays quiet — the setup fired only once.
    after = await s.on_bar_completed(_bar(5, 100.5, 100.7, 100.1, 100.3))
    assert after is None
    assert s._armed is None


async def test_next_bar_touches_sl_skips_entry() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s)
    sig = await s.on_bar_completed(_bar(4, *_SLHIT_LONG))
    assert sig is None  # touched level but breached SL first
    assert s._armed is None


async def test_long_sl_uses_pattern_low_minus_buffer() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s)
    sig = await s.on_bar_completed(_bar(4, *_TOUCH_LONG))
    assert sig is not None
    assert sig.stop_loss_price == pytest.approx(_LONG_SL)
    assert sig.stop_loss_price < _TOUCH_LONG[2]  # SL below the entry bar's low


async def test_long_tp_takes_rr_when_swing_near() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s, filler_high=100.0)  # window highs <= 100.5
    sig = await s.on_bar_completed(_bar(4, *_TOUCH_LONG))
    assert sig is not None
    entry = _TOUCH_LONG[3]
    assert sig.take_profit_price == pytest.approx(entry + (entry - _LONG_SL))


async def test_long_tp_takes_key_level_when_swing_far() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s, filler_high=110.0)  # far prior swing high outranks RR TP
    sig = await s.on_bar_completed(_bar(4, *_TOUCH_LONG))
    assert sig is not None
    assert sig.take_profit_price == pytest.approx(110.0)


async def test_short_mirror_touch_high() -> None:
    s = await _strategy(direction="short")
    armed = await _arm_short(s)
    assert armed is None
    assert s._armed is not None and s._armed["direction"] == Direction.SHORT
    sig = await s.on_bar_completed(_bar(4, *_TOUCH_SHORT))
    assert sig is not None
    assert sig.direction == Direction.SHORT
    assert sig.entry_price == pytest.approx(_TOUCH_SHORT[3])  # close(N+1) == 97.5
    assert sig.entry_logic == "engulfing_pullback30_touch:bearish"
    assert sig.stop_loss_price == pytest.approx(_SHORT_SL)
    entry = _TOUCH_SHORT[3]
    assert sig.take_profit_price == pytest.approx(entry - (_SHORT_SL - entry))
    assert sig.take_profit_price < entry


async def test_direction_long_only_ignores_bearish() -> None:
    s = await _strategy(direction="long")
    armed = await _arm_short(s)
    assert armed is None
    assert s._armed is None  # never armed a short


async def test_direction_short_only_ignores_bullish() -> None:
    s = await _strategy(direction="short")
    armed = await _arm_long(s)
    assert armed is None
    assert s._armed is None


async def test_pullback_pct_param_shifts_level() -> None:
    shallow = await _strategy(direction="long", pullback=0.30)
    await _arm_long(shallow)
    assert shallow._armed is not None
    assert shallow._armed["level"] == pytest.approx(99.8)

    deep = await _strategy(direction="long", pullback=0.50)
    await _arm_long(deep)
    assert deep._armed is not None
    assert deep._armed["level"] == pytest.approx(99.0)  # 101 - 0.5*4

    # A bar touching the 0.30 level (low 99.5) misses the deeper 0.50 level.
    miss = await deep.on_bar_completed(_bar(4, *_TOUCH_LONG))
    assert miss is None


async def test_position_cap_blocks_until_close() -> None:
    s = await _strategy(direction="long")
    await _arm_long(s)
    entry = await s.on_bar_completed(_bar(4, *_TOUCH_LONG))
    assert entry is not None
    await s.on_order_filled(_fill_order(OrderSide.BUY), fill_price=100.2)
    assert s._open_direction == Direction.LONG

    # New engulfing while a position is open — cap blocks the arm.
    await s.on_bar_completed(_bar(5, 100.0, 100.5, 97.5, 98.0))  # prev red
    await s.on_bar_completed(_bar(6, 97.0, 101.2, 96.8, 101.0))  # green engulf
    assert s._armed is None

    # Opposite-side fill closes the round trip → cap released, arming allowed.
    await s.on_order_filled(_fill_order(OrderSide.SELL), fill_price=101.5)
    assert s._open_direction is None
    await s.on_bar_completed(_bar(7, 100.0, 100.5, 97.5, 98.0))  # prev red
    rearm = await s.on_bar_completed(_bar(8, 97.0, 101.2, 96.8, 101.0))  # green engulf
    assert rearm is None
    assert s._armed is not None and s._armed["direction"] == Direction.LONG


@pytest.mark.parametrize(
    "params",
    [
        {"direction": "weird"},
        {"max_rejection_wick_pct": 0.0},
        {"max_rejection_wick_pct": 1.5},
        {"key_level_lookback_bars": 0},
        {"sl_buffer_pct": -0.1},
        {"pullback_pct": 0.0},
        {"pullback_pct": 1.0},
        {"pullback_pct": -0.1},
    ],
)
def test_invalid_params_raise_value_error(params: dict) -> None:
    cfg = StrategyConfig(id="bad", name="bad", symbol=_SYM, interval="1m", parameters=params)
    with pytest.raises(ValueError):
        EngulfingPullback30TouchStrategyService(cfg)
