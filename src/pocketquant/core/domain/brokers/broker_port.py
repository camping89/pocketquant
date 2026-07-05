from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate, TradeClosedEvent

# Callback can be sync or async
OrderCallback = Callable[[OrderResult], None | Awaitable[None]]
TradeCallback = Callable[[TradeClosedEvent], None | Awaitable[None]]


class IBrokerPort(ABC):
    """Abstract broker interface for order execution.

    Implementations:
    - PaperBrokerAdapter: Simulated fills for backtesting/paper trading
    - OKXBrokerAdapter: Live trading via OKX exchange API
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def submit_order(self, order: OrderAggregate) -> OrderResult:
        """Submit order to broker.

        Args:
            order: Order aggregate to submit

        Returns:
            OrderResult with broker order ID and status
        """
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order by broker order ID.

        Args:
            broker_order_id: The broker-assigned order ID

        Returns:
            True if cancellation request accepted
        """
        ...

    @abstractmethod
    async def get_positions(self) -> list[PositionAggregate]:
        """Get all open positions from broker.

        Returns:
            List of position aggregates
        """
        ...

    @abstractmethod
    async def get_balance(self) -> AccountBalance:
        """Get account balance from broker.

        Returns:
            Account balance details
        """
        ...

    @abstractmethod
    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        """Subscribe to order status updates.

        Args:
            callback: Function to call on order updates (sync or async)
        """
        ...

    @abstractmethod
    async def unsubscribe_order_updates(self) -> None:
        """Unsubscribe from order updates."""
        ...

    @abstractmethod
    async def subscribe_trades(self, callback: TradeCallback) -> None:
        """Subscribe to round-trip trade closures (average-cost).

        Fires a ``TradeClosedEvent`` for each position reduce/close, dispatched
        AFTER the corresponding fill ``OrderResult`` so back-links resolve.

        Args:
            callback: Function to call on trade closures (sync or async)
        """
        ...

    @abstractmethod
    async def unsubscribe_trades(self) -> None:
        """Unsubscribe from trade closures."""
        ...
