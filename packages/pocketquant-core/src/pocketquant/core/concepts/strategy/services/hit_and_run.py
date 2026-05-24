"""HitAndRun Strategy — double/triple bottom/top with ATR clustering."""

from collections import deque
from datetime import UTC, datetime

from pocketquant.core.concepts.strategy.enums import Direction
from pocketquant.core.concepts.strategy.interfaces import IStrategy
from pocketquant.core.concepts.strategy.value_objects import Signal, StrategyConfig


class HitAndRunStrategy(IStrategy):
    """Hit-and-Run Strategy.

    Detects double/triple bottoms (for long) or tops (for short) using
    ATR-based clustering, with SMA trend filter. SL/TP derived from
    lookback range ± offset_pct.

    Parameters (from YAML):
        lookback: Number of bars to scan (default: 10)
        atr_period: ATR calculation period (default: 14)
        bottom_atr_mult: Proximity threshold in ATR units (default: 0.5)
        min_bottoms: Min lows/highs in cluster (default: 2)
        ma_period: SMA trend filter period (default: 20)
        sl_offset_pct: SL offset from extreme (default: 0.10)
        tp_offset_pct: TP offset from extreme (default: 0.10)
        direction: "long", "short", or "both" (default: "both")
    """

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)

        self.lookback = int(config.parameters.get("lookback", 10))
        self.atr_period = int(config.parameters.get("atr_period", 14))
        self.bottom_atr_mult = float(config.parameters.get("bottom_atr_mult", 0.5))
        self.min_bottoms = int(config.parameters.get("min_bottoms", 2))
        self.ma_period = int(config.parameters.get("ma_period", 20))
        self.sl_offset_pct = float(config.parameters.get("sl_offset_pct", 0.10))
        self.tp_offset_pct = float(config.parameters.get("tp_offset_pct", 0.10))
        self.direction = str(config.parameters.get("direction", "both"))

        self._min_bars = max(self.atr_period, self.ma_period, self.lookback)
        self._closes: deque[float] = deque(maxlen=self._min_bars + 1)
        self._highs: deque[float] = deque(maxlen=self._min_bars + 1)
        self._lows: deque[float] = deque(maxlen=self._min_bars + 1)

        self._prev_close: float | None = None
        self._atr: float | None = None
        self._in_long = False
        self._in_short = False

    async def on_start(self) -> None:
        await super().on_start()
        self._closes.clear()
        self._highs.clear()
        self._lows.clear()
        self._prev_close = None
        self._atr = None
        self._in_long = False
        self._in_short = False

    async def on_bar(self, bar: dict) -> Signal | None:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        # Update ATR before appending (needs prev_close)
        if self._prev_close is not None:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
            if self._atr is None:
                self._atr = tr
            else:
                n = self.atr_period
                self._atr = self._atr * (n - 1) / n + tr / n

        self._closes.append(close)
        self._highs.append(high)
        self._lows.append(low)
        self._prev_close = close

        if len(self._closes) < self._min_bars or self._atr is None:
            return None

        ma = self._calc_sma(list(self._closes), self.ma_period)
        atr = self._atr
        lows = list(self._lows)[-self.lookback:]
        highs = list(self._highs)[-self.lookback:]

        signal = None

        if self.direction in ("long", "both") and not self._in_long:
            if close < ma:
                zone = self._find_cluster_zone(lows, atr)
                if zone is not None and low <= zone + self.bottom_atr_mult * atr:
                    signal = self._create_long_signal(close, lows, highs, bar)
                    if signal:
                        self._in_long = True

        if signal is None and self.direction in ("short", "both") and not self._in_short:
            if close > ma:
                zone = self._find_cluster_zone(highs, atr)
                if zone is not None and high >= zone - self.bottom_atr_mult * atr:
                    signal = self._create_short_signal(close, lows, highs, bar)
                    if signal:
                        self._in_short = True

        return signal

    def _calc_sma(self, prices: list[float], period: int) -> float:
        tail = prices[-period:]
        return sum(tail) / len(tail)

    def _find_cluster_zone(self, values: list[float], atr: float) -> float | None:
        """Return mean of largest cluster if it has >= min_bottoms members."""
        threshold = self.bottom_atr_mult * atr
        best: list[float] = []
        for anchor in values:
            cluster = [v for v in values if abs(v - anchor) <= threshold]
            if len(cluster) >= self.min_bottoms and len(cluster) > len(best):
                best = cluster
        return sum(best) / len(best) if best else None

    def _create_long_signal(
        self, close: float, lows: list[float], highs: list[float], bar: dict
    ) -> Signal:
        sl = min(lows) * (1 - self.sl_offset_pct)
        tp = max(highs) * (1 + self.tp_offset_pct)
        return Signal(
            symbol=self.config.symbol,
            direction=Direction.LONG,
            confidence=0.75,
            timestamp=bar.get("timestamp") or datetime.now(UTC),
            strategy_id=self.id,
            entry_price=close,
            stop_loss_price=sl,
            take_profit_price=tp,
            entry_logic=f"HitAndRun long: bottom cluster, close={close:.4f}, SL={sl:.4f}, TP={tp:.4f}",
        )

    def _create_short_signal(
        self, close: float, lows: list[float], highs: list[float], bar: dict
    ) -> Signal:
        sl = max(highs) * (1 + self.sl_offset_pct)
        tp = min(lows) * (1 - self.tp_offset_pct)
        return Signal(
            symbol=self.config.symbol,
            direction=Direction.SHORT,
            confidence=0.75,
            timestamp=bar.get("timestamp") or datetime.now(UTC),
            strategy_id=self.id,
            entry_price=close,
            stop_loss_price=sl,
            take_profit_price=tp,
            entry_logic=f"HitAndRun short: top cluster, close={close:.4f}, SL={sl:.4f}, TP={tp:.4f}",
        )

    async def on_fill(self, order: object, fill_price: float) -> None:
        pass
