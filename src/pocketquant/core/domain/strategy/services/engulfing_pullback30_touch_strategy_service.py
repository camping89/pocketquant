"""Engulfing pullback-30 touch — deferred entry on an intrabar retrace.

Variant of ``engulfing``: the qualifying engulfing bar does NOT enter. It arms a
one-bar setup; the very next bar enters at market (its close) only if price
retraces intrabar to ``pullback_pct`` of the engulfing body without first
breaching the stop. Reuses ``detect_engulfing`` and the parent's key-level and
fill-driven position-cap machinery; only the entry timing differs.

    Arm (LONG, bullish) at bar N:
      level = close_N - pullback_pct*(close_N - open_N)
      pattern_low = min(low_N, low_prev); SL = pattern_low*(1-buf)
      key_high = max(prev N highs)   # snapshot at bar N, excludes bar N
    Resolve at bar N+1:
      touch  = low(N+1) <= level; sl_hit = low(N+1) <= SL
      enter iff touch and not sl_hit and entry > SL, with entry = close(N+1)
      TP = max(entry + (entry - SL), key_high)
    SHORT mirrors: level = close_N + pullback_pct*(open_N - close_N);
      pattern_high = max(high_N, high_prev); SL = pattern_high*(1+buf);
      touch = high(N+1) >= level; sl_hit = high(N+1) >= SL; enter iff entry < SL;
      TP = min(entry - (SL - entry), key_low).

The setup lives for exactly one bar: a miss or SL breach discards it, and the
resolve bar never re-arms (it is spent resolving, not detecting). Single TP, at
most one open position via the fill-confirmed ``_open_direction`` cap.
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
    "pullback_pct": 0.30,  # retrace depth into the engulfing body
}


class EngulfingPullback30TouchStrategyService(IStrategyService):
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
        self.pullback_pct = float(p.get("pullback_pct", _DEFAULTS["pullback_pct"]))

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
        if not 0.0 < self.pullback_pct < 1.0:
            raise ValueError(f"pullback_pct must be in (0, 1), got {self.pullback_pct}")

        # maxlen=N (no +1): the window is snapshotted BEFORE the current bar is
        # appended, so it already holds exactly the N bars strictly before now.
        self._highs: deque[float] = deque(maxlen=self.key_level_lookback_bars)
        self._lows: deque[float] = deque(maxlen=self.key_level_lookback_bars)
        self._prev_bar: dict | None = None
        self._open_direction: Direction | None = None
        self._armed: dict | None = None

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._prev_bar = None
        self._open_direction = None
        self._armed = None

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

        # An armed setup means THIS is bar N+1 — resolve it and stop. The resolve
        # bar is spent here; it never falls through to arm a new setup.
        if self._armed is not None:
            signal = self._resolve_armed(bar, high, low)
            self._armed = None
            self._prev_bar = bar
            return signal

        if self._open_direction is not None:
            self._prev_bar = bar
            return None

        prev = self._prev_bar
        if prev is None:
            self._prev_bar = bar
            return None

        self._arm_if_pattern(prev, bar, high, low, key_highs, key_lows)
        self._prev_bar = bar
        return None

    def _arm_if_pattern(
        self,
        prev: dict,
        bar: dict,
        high: float,
        low: float,
        key_highs: list[float],
        key_lows: list[float],
    ) -> None:
        res = detect_engulfing(prev, bar)
        open_n = float(bar["open"])
        close_n = float(bar["close"])

        if (
            res.is_bullish
            and self.direction in ("long", "both")
            and res.rejection_wick_pct <= self.max_rejection_wick_pct
        ):
            level = close_n - self.pullback_pct * (close_n - open_n)
            pattern_low = min(low, float(prev["low"]))
            sl = pattern_low * (1 - self.sl_buffer_pct)
            self._armed = {
                "direction": Direction.LONG,
                "level": level,
                "sl": sl,
                "key_level_extreme": max(key_highs),
                "tag": "bullish",
            }
        elif (
            res.is_bearish
            and self.direction in ("short", "both")
            and res.rejection_wick_pct <= self.max_rejection_wick_pct
        ):
            level = close_n + self.pullback_pct * (open_n - close_n)
            pattern_high = max(high, float(prev["high"]))
            sl = pattern_high * (1 + self.sl_buffer_pct)
            self._armed = {
                "direction": Direction.SHORT,
                "level": level,
                "sl": sl,
                "key_level_extreme": min(key_lows),
                "tag": "bearish",
            }

    def _resolve_armed(self, bar: dict, high: float, low: float) -> Signal | None:
        armed = self._armed
        assert armed is not None
        entry = float(bar["close"])
        sl = armed["sl"]
        level = armed["level"]
        key = armed["key_level_extreme"]

        if armed["direction"] == Direction.LONG:
            if low > level or low <= sl or entry <= sl:
                return None
            tp = max(entry + (entry - sl), key)
            return self._mk_signal(Direction.LONG, bar, entry, sl, tp, "bullish")

        if high < level or high >= sl or entry >= sl:
            return None
        tp = min(entry - (sl - entry), key)
        return self._mk_signal(Direction.SHORT, bar, entry, sl, tp, "bearish")

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
            entry_logic=f"engulfing_pullback30_touch:{tag}",
        )
