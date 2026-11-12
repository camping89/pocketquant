from __future__ import annotations

import math
from collections import deque
from typing import ClassVar

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


def _ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


class TripleScreenStrategyService(IStrategyService):
    DEFAULTS: ClassVar[dict] = {
        "entry_type": "market",
        "exit_mode": "sl_tp",
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "force_period": 2,
        "stoploss_lookback": 2,
        "takeprofit_lookback": 0,
        "entry_buffer_atr": 0.0,
        "stoploss_buffer_atr": 0.0,
        "min_stop_atr": 0.0,
        "risk_reward": 2.0,
    }

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        p = config.parameters or {}
        d = self.DEFAULTS
        self.entry_type = p.get("entry_type", d["entry_type"])
        self.exit_mode = p.get("exit_mode", d["exit_mode"])
        self.macd_fast = p.get("macd_fast", d["macd_fast"])
        self.macd_slow = p.get("macd_slow", d["macd_slow"])
        self.macd_signal = p.get("macd_signal", d["macd_signal"])
        self.force_period = p.get("force_period", d["force_period"])
        self.stoploss_lookback = p.get("stoploss_lookback", d["stoploss_lookback"])
        self.takeprofit_lookback = p.get("takeprofit_lookback", d["takeprofit_lookback"])
        self.entry_buffer_atr = float(p.get("entry_buffer_atr", d["entry_buffer_atr"]))
        self.stoploss_buffer_atr = float(p.get("stoploss_buffer_atr", d["stoploss_buffer_atr"]))
        self.min_stop_atr = float(p.get("min_stop_atr", d["min_stop_atr"]))
        self.risk_reward = float(p.get("risk_reward", d["risk_reward"]))
        if len(config.intervals) != 3:
            raise ValueError("triple screen needs exactly 3 intervals: entry, middle, top")
        if self.entry_type not in ("market", "stop"):
            raise ValueError(f"entry_type must be market|stop, got {self.entry_type!r}")
        if self.exit_mode not in ("sl_tp", "strategy"):
            raise ValueError(f"exit_mode must be sl_tp|strategy, got {self.exit_mode!r}")
        counts = (
            self.macd_fast,
            self.macd_slow,
            self.macd_signal,
            self.force_period,
            self.stoploss_lookback,
        )
        if any(n < 1 for n in counts):
            raise ValueError("macd periods, force_period and stoploss_lookback must be >= 1")
        if self.takeprofit_lookback < 0:
            raise ValueError("takeprofit_lookback must be >= 0")
        for name in ("entry_buffer_atr", "stoploss_buffer_atr", "min_stop_atr"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0):
                raise ValueError(f"{name} must be a finite number >= 0")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be below macd_slow")
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be above 0")
        entry_interval, middle, _ = config.intervals
        # Lookbacks count bars of the middle interval; the window holds entry bars.
        self._ratio = INTERVAL_SECONDS[middle] // INTERVAL_SECONDS[entry_interval]
        window = max(self.stoploss_lookback, self.takeprofit_lookback) * self._ratio
        # Live warm-up replays 500 entry bars (_WARMUP_BARS in
        # engine/strategy/strategy_app_service.py), so a longer window would start live
        # trading on a shorter window than the backtest used.
        if window > 500:
            raise ValueError(
                "stoploss_lookback and takeprofit_lookback times the middle-to-entry ratio"
                f" must be at most 500 entry bars, got {window}"
            )
        self._recent: deque[tuple[float, float]] = deque(maxlen=window)
        self._reset()

    def _reset(self) -> None:
        self._recent.clear()
        self._open_direction = None
        # The side of the stop the strategy believes rests in the broker.
        self._armed: Direction | None = None
        self._sent: str | None = None
        self._armed_before_exit: Direction | None = None

    async def on_start(self) -> None:
        await super().on_start()
        self._reset()

    def _tide_slope(self, bars: list[Bar]) -> float | None:
        if len(bars) < self.macd_slow + self.macd_signal + 1:
            return None
        closes = [b.close for b in bars]
        fast, slow = _ema(closes, self.macd_fast), _ema(closes, self.macd_slow)
        macd = [f - s for f, s in zip(fast, slow, strict=True)]
        hist = [m - s for m, s in zip(macd, _ema(macd, self.macd_signal), strict=True)]
        return hist[-1] - hist[-2]

    # Wilder ATR(14) over the given closed bars.
    def _atr(self, bars: list[Bar]) -> float | None:
        if len(bars) < 15:
            return None
        ranges = [
            max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
            for a, b in zip(bars, bars[1:], strict=False)
        ]
        atr = sum(ranges[:14]) / 14
        for r in ranges[14:]:
            atr = (atr * 13 + r) / 14
        return atr

    def _force(self, bars: list[Bar]) -> float | None:
        if len(bars) < self.force_period + 1:
            return None
        raw = [(b.close - a.close) * b.volume for a, b in zip(bars, bars[1:], strict=False)]
        return _ema(raw, self.force_period)[-1]

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        self._recent.append((high, low))
        entry_interval, middle, top = self.config.intervals
        slope = self._tide_slope(bar["context"][top])
        force = self._force(bar["context"][middle])
        tide = None if slope is None else "up" if slope > 0 else "down" if slope < 0 else "flat"
        long_setup = tide == "up" and force is not None and force < 0
        short_setup = tide == "down" and force is not None and force > 0

        atr = self._atr(bar["context"][top])
        uses_atr = bool(self.entry_buffer_atr or self.stoploss_buffer_atr or self.min_stop_atr)

        signal: Signal | None = None
        price: float | None = None
        swing: float | None = None
        sl: float | None = None
        tp: float | None = None
        if slope is None or (uses_atr and atr is None):
            action, reason = "skip", "top interval warming up"
        elif force is None:
            action, reason = "skip", "middle interval warming up"
        elif self._open_direction is not None:
            against = "down" if self._open_direction == Direction.LONG else "up"
            if self.exit_mode == "strategy" and tide == against:
                action, reason = "exit", "tide turned against the position"
            else:
                action, reason = "hold", "position held"
        elif long_setup or short_setup:
            direction = Direction.LONG if long_setup else Direction.SHORT
            stop = self.entry_type == "stop"
            # atr is None here only when every ATR parameter is 0.
            x = atr or 0.0
            recent = list(self._recent)
            sl_bars = recent[-self.stoploss_lookback * self._ratio :]
            if long_setup:
                price = high + self.entry_buffer_atr * x if stop else close
                swing = min(lo for _, lo in sl_bars) - self.stoploss_buffer_atr * x
                sl = min(swing, price - self.min_stop_atr * x)
                risk = price - sl
            else:
                price = low - self.entry_buffer_atr * x if stop else close
                swing = max(h for h, _ in sl_bars) + self.stoploss_buffer_atr * x
                sl = max(swing, price + self.min_stop_atr * x)
                risk = sl - price
            if risk <= 0:
                action, reason, price = "skip", "no risk distance", None
            else:
                action = "enter_long" if long_setup else "enter_short"
                reason = (
                    "tide up, force below zero" if long_setup else "tide down, force above zero"
                )
                if self.exit_mode == "sl_tp":
                    sign = 1 if long_setup else -1
                    tp = price + sign * self.risk_reward * risk
                    if self.takeprofit_lookback > 0:
                        tp_bars = recent[-self.takeprofit_lookback * self._ratio :]
                        if long_setup:
                            tp = max(max(h for h, _ in tp_bars), tp)
                        else:
                            tp = min(min(lo for _, lo in tp_bars), tp)
                signal = self._signal(bar, direction, action, price, sl, tp)
                # Re-sent every bar while the setup holds: no resting stop survives a restart,
                # and the engine keeps an unchanged one.
                if stop:
                    self._armed = direction
                else:
                    self._open_direction = direction
        elif self._armed is not None:
            action, reason = "exit", "setup gone"
        else:
            action, reason = "hold", "no setup"

        if action == "exit":
            self._armed_before_exit, self._armed = self._armed, None
            signal = self._signal(bar, Direction.EXIT, action)
        self._sent = None if signal is None else "exit" if action == "exit" else self.entry_type
        self.snapshot = {
            "readings": [
                {
                    "interval": top,
                    "name": "macd_hist_slope",
                    "value": slope,
                    "ok": tide in ("up", "down"),
                },
                {
                    "interval": middle,
                    "name": "force_index",
                    "value": force,
                    "ok": long_setup or short_setup,
                },
                {
                    "interval": entry_interval,
                    "name": "trigger",
                    "value": price,
                    "ok": signal is not None,
                },
                {"interval": top, "name": "atr", "value": atr, "ok": None},
                {"interval": entry_interval, "name": "swing_stop", "value": swing, "ok": None},
                {"interval": entry_interval, "name": "sl", "value": sl, "ok": None},
                {"interval": entry_interval, "name": "tp", "value": tp, "ok": None},
            ],
            "decision": {"action": action, "reason": reason},
        }
        return signal

    def _signal(
        self,
        bar: dict,
        direction: Direction,
        action: str,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Signal:
        return Signal(
            symbol=self.config.symbol,
            direction=direction,
            confidence=0.7,
            timestamp=bar["timestamp"],
            subscription_id=self.id,
            entry_price=price,
            stop_loss_price=sl,
            take_profit_price=tp,
            entry_logic=f"triple_screen:{action}",
            entry_type="stop" if self.entry_type == "stop" and price is not None else "market",
        )

    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        if self._open_direction is None:
            self._open_direction = (
                Direction.LONG if order.side == OrderSide.BUY else Direction.SHORT
            )
            self._armed = None
            return
        closing = OrderSide.SELL if self._open_direction == Direction.LONG else OrderSide.BUY
        if order.side == closing:
            self._open_direction = None

    # A rejection undoes only what the rejected signal changed, so a rejected EXIT is
    # retried on the next bar.
    async def on_order_rejected(self, reason: str) -> None:
        if self._sent == "market":
            self._open_direction = None
        elif self._sent == "exit":
            self._armed = self._armed_before_exit
        self._sent = None
