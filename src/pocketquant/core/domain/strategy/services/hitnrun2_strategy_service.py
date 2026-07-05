"""HitNRun2 — 1m breakdown buy / breakup sell with technical SL/TP and account caps.

Entry rules (LONG):
    On a closed bar, if ``close`` breaks below ``min(prev_lows[-entry_lookback:])``
    (excluding the current bar), emit a LONG signal at ``close``.

Entry rules (SHORT): mirror — break above the prior-window high.

SL/TP per side are the **looser** of the technical level and the account cap:
    LONG  SL = MAX( min(prev_lows[-sl_lookback:]), entry * (1 - max_loss_pct) )
    LONG  TP = MAX( max(prev_highs[-tp_lookback:]), entry * (1 + min_profit_pct) )
    SHORT SL = MIN( max(prev_highs[-sl_lookback:]), entry * (1 + max_loss_pct) )
    SHORT TP = MIN( min(prev_lows[-tp_lookback:]),  entry * (1 - min_profit_pct) )

At most one open position. State is reset by ``on_order_filled`` when an
opposite-side fill closes the open direction; the PaperBrokerAdapter SL/TP auto-fill
drives this.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig

_DEFAULTS = {
    "entry_lookback_bars": 240,  # 4h on 1m bars
    "sl_lookback_bars": 480,  # 8h on 1m bars
    "tp_lookback_bars": 60,  # 1h on 1m bars
    "max_loss_pct": 0.01,  # cap loss at 1% of entry
    "min_profit_pct": 0.02,  # require >= 2% profit target
    "direction": "both",  # "long" | "short" | "both"
}


class HitNRun2StrategyService(IStrategyService):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        p = config.parameters or {}
        self.entry_lookback_bars = int(
            p.get("entry_lookback_bars", _DEFAULTS["entry_lookback_bars"])
        )
        self.sl_lookback_bars = int(p.get("sl_lookback_bars", _DEFAULTS["sl_lookback_bars"]))
        self.tp_lookback_bars = int(p.get("tp_lookback_bars", _DEFAULTS["tp_lookback_bars"]))
        self.max_loss_pct = float(p.get("max_loss_pct", _DEFAULTS["max_loss_pct"]))
        self.min_profit_pct = float(p.get("min_profit_pct", _DEFAULTS["min_profit_pct"]))
        self.direction = str(p.get("direction", _DEFAULTS["direction"])).lower()
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")

        # +1 keeps room for the current bar being appended after window snapshot.
        self._buffer_size = (
            max(self.entry_lookback_bars, self.sl_lookback_bars, self.tp_lookback_bars) + 1
        )
        self._highs: deque[float] = deque(maxlen=self._buffer_size)
        self._lows: deque[float] = deque(maxlen=self._buffer_size)
        self._closes: deque[float] = deque(maxlen=self._buffer_size)
        self._open_direction: Direction | None = None

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._closes.clear()
        self._open_direction = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        # Snapshot windows BEFORE appending current bar so the current bar is excluded.
        prev_lows_entry = list(self._lows)[-self.entry_lookback_bars :]
        prev_highs_entry = list(self._highs)[-self.entry_lookback_bars :]
        prev_lows_sl = list(self._lows)[-self.sl_lookback_bars :]
        prev_highs_sl = list(self._highs)[-self.sl_lookback_bars :]
        prev_lows_tp = list(self._lows)[-self.tp_lookback_bars :]
        prev_highs_tp = list(self._highs)[-self.tp_lookback_bars :]

        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        # Warmup: need sl_lookback_bars closed bars BEFORE current.
        if len(prev_lows_sl) < self.sl_lookback_bars:
            return None

        # Position cap — only one open position at a time.
        if self._open_direction is not None:
            return None

        if self.direction in ("long", "both") and prev_lows_entry:
            prev_low_4h = min(prev_lows_entry)
            if close < prev_low_4h:
                sl = max(min(prev_lows_sl), close * (1 - self.max_loss_pct))
                tp = max(max(prev_highs_tp), close * (1 + self.min_profit_pct))
                self._open_direction = Direction.LONG
                return self._mk_signal(Direction.LONG, close, sl, tp, bar, "breakdown")

        if self.direction in ("short", "both") and prev_highs_entry:
            prev_high_4h = max(prev_highs_entry)
            if close > prev_high_4h:
                sl = min(max(prev_highs_sl), close * (1 + self.max_loss_pct))
                tp = min(min(prev_lows_tp), close * (1 - self.min_profit_pct))
                self._open_direction = Direction.SHORT
                return self._mk_signal(Direction.SHORT, close, sl, tp, bar, "breakup")

        return None

    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        """Reset open-direction when the broker closes our position.

        Broker SL/TP auto-fill emits the opposite side (SELL closes LONG,
        BUY closes SHORT). Treat any opposite-side fill as the round-trip close.
        """
        side = getattr(order, "side", None)
        if self._open_direction == Direction.LONG and side == OrderSide.SELL:
            self._open_direction = None
        elif self._open_direction == Direction.SHORT and side == OrderSide.BUY:
            self._open_direction = None

    def _mk_signal(
        self,
        direction: Direction,
        close: float,
        sl: float,
        tp: float,
        bar: dict[str, Any],
        tag: str,
    ) -> Signal:
        timestamp = bar.get("timestamp") or datetime.now(UTC)
        return Signal(
            symbol=self.config.symbol,
            direction=direction,
            confidence=0.7,
            timestamp=timestamp,
            subscription_id=self.id,
            entry_price=close,
            stop_loss_price=sl,
            take_profit_price=tp,
            entry_logic=f"hitnrun2:{tag}",
        )
