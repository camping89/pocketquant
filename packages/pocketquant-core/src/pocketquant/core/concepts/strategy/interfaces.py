"""Strategy interface - base class for all trading strategies."""

from abc import ABC, abstractmethod

from pocketquant.core.concepts.strategy.value_objects import Signal, StrategyConfig
from pocketquant.core.domain.order import OrderAggregate


class IStrategy(ABC):
    """Abstract base class for trading strategies.

    Strategies implement trading logic and generate signals based on
    market data. The StrategyAppService calls hooks based on the trigger type.

    Lifecycle:
        1. __init__(config) - Initialize with configuration
        2. on_start() - Called when strategy starts
        3. on_bar()/on_tick() - Called on market data
        4. on_fill() - Called when orders are filled
        5. on_stop() - Called when strategy stops
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.id = config.id
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Check if strategy is currently running."""
        return self._is_running

    async def on_start(self) -> None:
        """Called when strategy starts. Override for initialization."""
        self._is_running = True

    async def on_stop(self) -> None:
        """Called when strategy stops. Override for cleanup."""
        self._is_running = False

    @abstractmethod
    async def on_bar(self, bar: dict) -> Signal | None:
        """Process completed bar, return signal if entry/exit.

        Args:
            bar: OHLCV bar data with keys: open, high, low, close, volume, timestamp

        Returns:
            Signal if strategy wants to enter/exit, None otherwise
        """
        ...

    async def on_tick(self, tick: dict) -> OrderAggregate | None:
        """Process tick for intra-bar adjustments (optional).

        Override this for tick-triggered strategies or for managing
        trailing stops and dynamic exits.

        Args:
            tick: Quote tick data with keys: price, bid, ask, timestamp

        Returns:
            Order modification if needed, None otherwise
        """
        return None

    async def on_fill(self, order: OrderAggregate, fill_price: float) -> None:
        """Called when an order is filled (optional).

        Override to update internal state after fills.

        Args:
            order: The filled order
            fill_price: Actual fill price
        """
        pass

    def get_parameter(self, key: str, default: object = None) -> object:
        """Get strategy parameter from config."""
        return self.config.parameters.get(key, default)
