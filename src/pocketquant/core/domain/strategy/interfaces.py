from abc import ABC, abstractmethod
from typing import Protocol

from pocketquant.core.domain.order import OrderAggregate, OrderSide
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


class FilledOrder(Protocol):
    """Structural type for ``on_order_filled``: any fill carrying a ``side``.

    Both ``OrderAggregate`` and ``OrderFilledEvent`` satisfy it, so the fill
    handler accepts either without coupling the strategy contract to the
    OrderFilledEvent routing. Declared read-only so a frozen-dataclass event
    (``OrderFilledEvent``) matches alongside the mutable ``OrderAggregate``.
    """

    @property
    def side(self) -> OrderSide: ...


class IStrategy(ABC):
    """Abstract base class for trading strategies.

    Strategies implement trading logic and generate signals based on
    market data. The StrategyAppService calls hooks based on the trigger type.

    Lifecycle:
        1. __init__(config) - Initialize with configuration
        2. on_start() - Called when strategy starts
        3. on_bar_completed()/on_quote_received() - Called on market data
        4. on_order_filled() - Called when orders are filled
        5. on_stop() - Called when strategy stops
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.id = config.id
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def on_start(self) -> None:
        self._is_running = True

    async def on_stop(self) -> None:
        self._is_running = False

    @abstractmethod
    async def on_bar_completed(self, bar: dict) -> Signal | None:
        """Process completed bar, return signal if entry/exit.

        Args:
            bar: OHLCV bar data with keys: open, high, low, close, volume, timestamp

        Returns:
            Signal if strategy wants to enter/exit, None otherwise
        """
        ...

    async def on_quote_received(self, tick: dict) -> OrderAggregate | None:
        """Process tick for intra-bar adjustments (optional).

        Override this for tick-triggered strategies or for managing
        trailing stops and dynamic exits.

        Args:
            tick: Quote tick data with keys: price, bid, ask, timestamp

        Returns:
            Order modification if needed, None otherwise
        """
        return None

    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        """Called when an order is filled (optional).

        Override to update internal state after fills. ``order`` is structural:
        the OrderFilledEvent handler passes the event itself, which carries the
        ``.side`` the strategy needs to detect a round-trip close.

        Args:
            order: The filled order (anything with ``.side: OrderSide``)
            fill_price: Actual fill price
        """
        pass

    def get_parameter(self, key: str, default: object = None) -> object:
        return self.config.parameters.get(key, default)
