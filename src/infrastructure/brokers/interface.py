"""Broker interface - abstract base class for all brokers."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from src.domain.order import OrderAggregate
from src.domain.position import PositionAggregate
from src.infrastructure.brokers.models import AccountBalance, OrderResult


class IBroker(ABC):
    """Abstract broker interface for order execution.

    Implementations:
    - PaperBroker: Simulated fills for backtesting/paper trading
    - OKXBroker: Live trading via OKX exchange API
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker identifier name."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if broker connection is active."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to broker."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close broker connection."""
        ...

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
    async def subscribe_order_updates(
        self, callback: Callable[[OrderResult], None]
    ) -> None:
        """Subscribe to order status updates.

        Args:
            callback: Function to call on order updates
        """
        ...

    @abstractmethod
    async def unsubscribe_order_updates(self) -> None:
        """Unsubscribe from order updates."""
        ...
