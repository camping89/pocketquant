"""Engulfing — full-candle engulfing entries with a directional quality filter.

A pattern qualifies only when the current bar covers the previous one on both
axes: body over body AND range over range (see ``detect_engulfing``). Entry: a
strong engulfing (rejection wick against the trade direction within
``max_rejection_wick_pct``) opens one position.

    LONG  entry=close; pattern_low=min(low_curr, low_prev); SL=pattern_low*(1-buf)
          risk=entry-SL; tp_rr=entry+risk; key=max(prev N highs); TP=max(tp_rr, key)
    SHORT mirror: pattern_high=max(high_curr, high_prev); SL=pattern_high*(1+buf)
          risk=SL-entry; tp_rr=entry-risk; key=min(prev N lows); TP=min(tp_rr, key)

Single TP, at most one open position. ``_open_direction`` is set when the entry
fill is confirmed (not optimistically on signal) so a rejected/zero-size entry
cannot wedge the cap; an opposite-side fill clears it on the round-trip close.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.patterns import detect_engulfing
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig

_DEFAULTS = {
    "direction": "both",  # "long" | "short" | "both"
    "sl_buffer_pct": 0.001,  # 0.1% below/above the pattern extreme
    "key_level_lookback_bars": 20,
    "max_rejection_wick_pct": 0.30,  # 1.0 disables the quality filter
}


class EngulfingStrategyService(IStrategyService):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        p = config.parameters or {}
        self.direction = str(p.get("direction", _DEFAULTS["direction"])).lower()
        self.sl_buffer_pct = float(p.get("sl_buffer_pct", _DEFAULTS["sl_buffer_pct"]))
        self.key_level_lookback_bars = int(
            p.get("key_level_lookback_bars", _DEFAULTS["key_level_lookback_bars"])
        )
        self.max_rejection_wick_pct = float(
            p.get("max_rejection_wick_pct", _DEFAULTS["max_rejection_wick_pct"])
        )

        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        if not 0.0 < self.max_rejection_wick_pct <= 1.0:
            raise ValueError(
                f"max_rejection_wick_pct must be in (0, 1], got {self.max_rejection_wick_pct}"
            )
        if self.key_level_lookback_bars < 1:
            raise ValueError(
                f"key_level_lookback_bars must be >= 1, got {self.key_level_lookback_bars}"
            )
        if self.sl_buffer_pct < 0:
            raise ValueError(f"sl_buffer_pct must be >= 0, got {self.sl_buffer_pct}")

        # maxlen=N (no +1): the window is snapshotted BEFORE the current bar is
        # appended, so it already holds exactly the N bars strictly before now.
        self._highs: deque[float] = deque(maxlen=self.key_level_lookback_bars)
        self._lows: deque[float] = deque(maxlen=self.key_level_lookback_bars)
        self._prev_bar: dict | None = None
        self._open_direction: Direction | None = None

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._prev_bar = None
        self._open_direction = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high = float(bar["high"])
        low = float(bar["low"])

        # Snapshot the key-level window BEFORE appending so it excludes the
        # current bar (and the pattern bar itself) — off-by-one guard.
        key_highs = list(self._highs)
        key_lows = list(self._lows)
        self._highs.append(high)
        self._lows.append(low)

        if len(key_highs) < self.key_level_lookback_bars:
            self._prev_bar = bar
            return None

        if self._open_direction is not None:
            self._prev_bar = bar
            return None

        prev = self._prev_bar
        if prev is None:
            self._prev_bar = bar
            return None

        res = detect_engulfing(prev, bar)
        signal: Signal | None = None

        if (
            res.is_bullish
            and self.direction in ("long", "both")
            and res.rejection_wick_pct <= self.max_rejection_wick_pct
        ):
            entry = float(bar["close"])
            pattern_low = min(low, float(prev["low"]))
            sl = pattern_low * (1 - self.sl_buffer_pct)
            tp_rr = entry + (entry - sl)
            tp = max(tp_rr, max(key_highs))
            signal = self._mk_signal(Direction.LONG, bar, entry, sl, tp, "bullish")

        elif (
            res.is_bearish
            and self.direction in ("short", "both")
            and res.rejection_wick_pct <= self.max_rejection_wick_pct
        ):
            entry = float(bar["close"])
            pattern_high = max(high, float(prev["high"]))
            sl = pattern_high * (1 + self.sl_buffer_pct)
            tp_rr = entry - (sl - entry)
            tp = min(tp_rr, min(key_lows))
            signal = self._mk_signal(Direction.SHORT, bar, entry, sl, tp, "bearish")

        self._prev_bar = bar
        return signal

    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        """Set the open direction on the entry fill; clear it on the close.

        While flat, the next fill is the entry — record its side as the open
        direction. While in a position, an opposite-side fill is the SL/TP
        round-trip close.
        """
        side = getattr(order, "side", None)
        if self._open_direction is None:
            if side == OrderSide.BUY:
                self._open_direction = Direction.LONG
            elif side == OrderSide.SELL:
                self._open_direction = Direction.SHORT
        elif self._open_direction == Direction.LONG and side == OrderSide.SELL:
            self._open_direction = None
        elif self._open_direction == Direction.SHORT and side == OrderSide.BUY:
            self._open_direction = None

    def _mk_signal(
        self,
        direction: Direction,
        bar: dict[str, Any],
        entry: float,
        sl: float,
        tp: float,
        tag: str,
    ) -> Signal:
        timestamp = bar.get("timestamp") or datetime.now(UTC)
        return Signal(
            symbol=self.config.symbol,
            direction=direction,
            confidence=0.7,
            timestamp=timestamp,
            subscription_id=self.id,
            entry_price=entry,
            stop_loss_price=sl,
            take_profit_price=tp,
            entry_logic=f"engulfing:{tag}",
        )
