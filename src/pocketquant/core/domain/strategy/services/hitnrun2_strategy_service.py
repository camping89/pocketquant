from __future__ import annotations

from collections import deque
from typing import ClassVar

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


class HitNRun2StrategyService(IStrategyService):
    DEFAULTS: ClassVar[dict] = {
        "entry_lookback_bars": 240,
        "sl_lookback_bars": 480,
        "tp_lookback_bars": 60,
        "max_loss_pct": 0.01,
        "min_profit_pct": 0.02,
        "direction": "both",
        "min_cost_multiple": 3.0,
    }

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        p = config.parameters or {}
        d = self.DEFAULTS
        self.entry_lookback_bars = p.get("entry_lookback_bars", d["entry_lookback_bars"])
        self.sl_lookback_bars = p.get("sl_lookback_bars", d["sl_lookback_bars"])
        self.tp_lookback_bars = p.get("tp_lookback_bars", d["tp_lookback_bars"])
        self.max_loss_pct = float(p.get("max_loss_pct", d["max_loss_pct"]))
        self.min_profit_pct = float(p.get("min_profit_pct", d["min_profit_pct"]))
        self.direction = p.get("direction", d["direction"])
        self.min_cost_multiple = float(p.get("min_cost_multiple", d["min_cost_multiple"]))
        lookbacks = (self.entry_lookback_bars, self.sl_lookback_bars, self.tp_lookback_bars)
        if len(config.intervals) != 1:
            raise ValueError("hitnrun2 decides on exactly one interval")
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        if any(n < 1 for n in lookbacks):
            raise ValueError("lookbacks must be >= 1")
        if self.max_loss_pct <= 0 or self.min_profit_pct < 0 or self.min_cost_multiple < 0:
            raise ValueError("max_loss_pct must be above 0; min_profit_pct, min_cost_multiple >= 0")
        spec = config.contract_spec
        # A fee on entry and on exit plus one spread, in price units on the seeded gold spec
        # (multiplier 1.0). A spec without a per-contract fee adds no commission here.
        self._round_trip = (spec.commission_per_contract or 0.0) * 2 + spec.spread
        self._highs: deque[float] = deque(maxlen=max(lookbacks))
        self._lows: deque[float] = deque(maxlen=max(lookbacks))

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._open_direction = None

    def _breakout(
        self, highs: list[float], lows: list[float], close: float
    ) -> tuple[Direction, float, float, str] | None:
        # LONG on a close below the entry-window low (SL below, TP above); SHORT mirrors.
        if self.direction != "short" and close < min(lows[-self.entry_lookback_bars :]):
            sl = max(min(lows[-self.sl_lookback_bars :]), close * (1 - self.max_loss_pct))
            tp = max(max(highs[-self.tp_lookback_bars :]), close * (1 + self.min_profit_pct))
            return Direction.LONG, sl, tp, "breakdown"
        if self.direction != "long" and close > max(highs[-self.entry_lookback_bars :]):
            sl = min(max(highs[-self.sl_lookback_bars :]), close * (1 + self.max_loss_pct))
            tp = min(min(lows[-self.tp_lookback_bars :]), close * (1 - self.min_profit_pct))
            return Direction.SHORT, sl, tp, "breakup"
        return None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        # Read before the current bar joins, so a bar never breaks its own range.
        highs, lows = list(self._highs), list(self._lows)
        self._highs.append(high)
        self._lows.append(low)

        signal = None
        if len(lows) < self.sl_lookback_bars:
            action, reason = "skip", "warming up"
        elif self._open_direction is not None:
            action, reason = "hold", "position held"
        elif (breakout := self._breakout(highs, lows, close)) is None:
            action, reason = "hold", "no breakout"
        else:
            direction, sl, tp, tag = breakout
            if direction == Direction.LONG:
                nearer = min(tp - close, close - sl)
            else:
                nearer = min(close - tp, sl - close)
            # A stop on the wrong side of the close gives a distance <= 0, which no cost covers.
            if nearer <= 0 or nearer < self.min_cost_multiple * self._round_trip:
                action, reason = "skip", "nearer exit under the cost multiple"
            else:
                action = "enter_long" if direction == Direction.LONG else "enter_short"
                reason = tag
                self._open_direction = direction
                signal = Signal(
                    symbol=self.config.symbol,
                    direction=direction,
                    confidence=0.7,
                    timestamp=bar["timestamp"],
                    subscription_id=self.id,
                    entry_price=close,
                    stop_loss_price=sl,
                    take_profit_price=tp,
                    entry_logic=f"hitnrun2:{tag}",
                )
        self.snapshot = {"readings": [], "decision": {"action": action, "reason": reason}}
        return signal

    # Broker SL/TP fills arrive as the opposite side, so an opposite-side fill is the close.
    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        if (self._open_direction == Direction.LONG and order.side == OrderSide.SELL) or (
            self._open_direction == Direction.SHORT and order.side == OrderSide.BUY
        ):
            self._open_direction = None

    # Only market entries are sent, so a rejection means no position opened.
    async def on_order_rejected(self, reason: str) -> None:
        self._open_direction = None
