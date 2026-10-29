from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime

from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate, TradeClosedEvent

# Callback can be sync or async
OrderCallback = Callable[[OrderResult], None | Awaitable[None]]
TradeCallback = Callable[[TradeClosedEvent], None | Awaitable[None]]


class IBrokerPort(ABC):
    # True when fills arrive later through subscribe_order_updates rather than
    # in the submit_order result; the engine then routes them to the order service.
    fills_async: bool = False

    # A trader hands over only at 0.
    @property
    def inflight_count(self) -> int:
        return 0

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

    # None when the broker cannot fill the size.
    async def normalize_quantity(self, symbol: str, quantity: float) -> float | None:
        return quantity

    # deadline is the trader's trading_until: the order is not sent at or after it. None
    # means no deadline (backtests, direct calls).
    @abstractmethod
    async def submit_order(
        self, order: OrderAggregate, *, deadline: datetime | None = None
    ) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> list[PositionAggregate]: ...

    @abstractmethod
    async def get_balance(self) -> AccountBalance: ...

    @abstractmethod
    async def subscribe_order_updates(self, callback: OrderCallback) -> None: ...

    @abstractmethod
    async def unsubscribe_order_updates(self) -> None: ...

    # Each TradeClosedEvent is dispatched after its fill OrderResult so back-links resolve.
    @abstractmethod
    async def subscribe_trades(self, callback: TradeCallback) -> None: ...

    @abstractmethod
    async def unsubscribe_trades(self) -> None: ...
