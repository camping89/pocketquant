"""Moving Average Crossover Strategy implementation."""

from collections import deque
from datetime import UTC, datetime

from src.domain.strategy.interfaces import IStrategy
from src.domain.strategy.value_objects import Direction, Signal, StrategyConfig


class MACrossoverStrategy(IStrategy):
    """Moving Average Crossover Strategy.

    Generates LONG signal when fast MA crosses above slow MA.
    Generates EXIT signal when fast MA crosses below slow MA.

    Parameters (from YAML):
        fast_period: Period for fast moving average (default: 10)
        slow_period: Period for slow moving average (default: 20)
        use_ema: Use EMA instead of SMA (default: True)
    """

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)

        # Get parameters from config
        self.fast_period = int(config.parameters.get("fast_period", 10))
        self.slow_period = int(config.parameters.get("slow_period", 20))
        self.use_ema = bool(config.parameters.get("use_ema", True))

        # Price history for MA calculation
        self._prices: deque[float] = deque(maxlen=self.slow_period)

        # EMA state
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None

        # Previous MA values for crossover detection
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

        # Position state
        self._in_position = False

    async def on_start(self) -> None:
        """Reset state on strategy start."""
        await super().on_start()
        self._prices.clear()
        self._fast_ema = None
        self._slow_ema = None
        self._prev_fast = None
        self._prev_slow = None
        self._in_position = False

    async def on_bar(self, bar: dict) -> Signal | None:
        """Process bar and generate signal on MA crossover."""
        close = bar["close"]
        self._prices.append(close)

        # Need enough data for slow MA
        if len(self._prices) < self.slow_period:
            return None

        # Calculate MAs
        if self.use_ema:
            fast_ma = self._calculate_ema(close, self.fast_period, self._fast_ema)
            slow_ma = self._calculate_ema(close, self.slow_period, self._slow_ema)
            self._fast_ema = fast_ma
            self._slow_ema = slow_ma
        else:
            fast_ma = self._calculate_sma(self.fast_period)
            slow_ma = self._calculate_sma(self.slow_period)

        signal = self._check_crossover(fast_ma, slow_ma, close, bar)

        # Update previous values
        self._prev_fast = fast_ma
        self._prev_slow = slow_ma

        return signal

    def _calculate_sma(self, period: int) -> float:
        """Calculate Simple Moving Average."""
        prices = list(self._prices)[-period:]
        return sum(prices) / len(prices)

    def _calculate_ema(
        self, price: float, period: int, prev_ema: float | None
    ) -> float:
        """Calculate Exponential Moving Average."""
        multiplier = 2 / (period + 1)

        if prev_ema is None:
            # Initialize with SMA
            return self._calculate_sma(period)

        return (price - prev_ema) * multiplier + prev_ema

    def _check_crossover(
        self, fast_ma: float, slow_ma: float, close: float, bar: dict
    ) -> Signal | None:
        """Check for MA crossover and generate signal."""
        if self._prev_fast is None or self._prev_slow is None:
            return None

        # Bullish crossover: fast crosses above slow
        if self._prev_fast <= self._prev_slow and fast_ma > slow_ma:
            if not self._in_position:
                self._in_position = True
                return self._create_signal(
                    Direction.LONG,
                    close,
                    bar,
                    f"Bullish crossover: fast={fast_ma:.2f} > slow={slow_ma:.2f}",
                )

        # Bearish crossover: fast crosses below slow
        elif self._prev_fast >= self._prev_slow and fast_ma < slow_ma:
            if self._in_position:
                self._in_position = False
                return self._create_signal(
                    Direction.EXIT,
                    close,
                    bar,
                    f"Bearish crossover: fast={fast_ma:.2f} < slow={slow_ma:.2f}",
                )

        return None

    def _create_signal(
        self, direction: Direction, close: float, bar: dict, logic: str
    ) -> Signal:
        """Create a trading signal."""
        # Calculate stop loss and take profit
        sl_distance = self.config.orders.stop_loss.distance_percent
        tp_distance = self.config.orders.take_profit.distance_percent

        if direction == Direction.LONG:
            stop_loss = close * (1 - sl_distance)
            take_profit = close * (1 + tp_distance)
        else:
            stop_loss = None
            take_profit = None

        return Signal(
            symbol=self.config.symbol,
            exchange=self.config.exchange,
            direction=direction,
            confidence=0.8,  # Fixed confidence for this strategy
            timestamp=bar.get("timestamp") or datetime.now(UTC),
            strategy_id=self.id,
            entry_price=close,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            entry_logic=logic,
        )

    async def on_fill(self, order: object, fill_price: float) -> None:
        """Update position state on fill."""
        # Position state already tracked via crossover logic
        pass
