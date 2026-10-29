from abc import ABC, abstractmethod
from typing import Protocol

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
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


class IStrategyService(ABC):
    """Abstract base class for trading strategies.

    Strategies implement trading logic and generate signals based on
    completed bars. The StrategyAppService calls the hooks below.

    Lifecycle:
        1. __init__(config) - Initialize with configuration
        2. on_start() - Called when strategy starts
        3. on_bar_completed() - Called on each completed bar
        4. on_order_filled() - Called when orders are filled
        5. on_stop() - Called when strategy stops
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.id = config.id
        self._is_running = False
        self._open_direction: Direction | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def on_start(self) -> None:
        self._is_running = True

    def restore_direction(self, direction: Direction | None) -> None:
        """Set the open direction from the stored position after a restart."""
        self._open_direction = direction

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

    async def on_order_rejected(self, reason: str) -> None:
        """Called when an entry signal ends without a fill (risk, size, minimum, broker reject)."""
        return None
