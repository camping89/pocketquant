from __future__ import annotations

from collections import deque
from typing import ClassVar

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
        "stop_lookback": 5,
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
        self.stop_lookback = p.get("stop_lookback", d["stop_lookback"])
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
            self.stop_lookback,
        )
        if any(n < 1 for n in counts):
            raise ValueError("macd periods, force_period and stop_lookback must be >= 1")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be below macd_slow")
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be above 0")
        self._recent: deque[tuple[float, float]] = deque(maxlen=self.stop_lookback)
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

        signal: Signal | None = None
        price: float | None = None
        if slope is None:
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
            if long_setup:
                price = high if stop else close
                sl = min(lo for _, lo in self._recent)
                risk = price - sl
            else:
                price = low if stop else close
                sl = max(h for h, _ in self._recent)
                risk = sl - price
            if risk <= 0:
                action, reason, price = "skip", "no risk distance", None
            else:
                action = "enter_long" if long_setup else "enter_short"
                reason = (
                    "tide up, force below zero" if long_setup else "tide down, force above zero"
                )
                tp = None
                if self.exit_mode == "sl_tp":
                    sign = 1 if long_setup else -1
                    tp = price + sign * self.risk_reward * risk
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
