from abc import ABC, abstractmethod
from typing import Protocol

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


# Both OrderAggregate and OrderFilledEvent satisfy it. Read-only so the frozen
# dataclass event matches alongside the mutable aggregate.
class FilledOrder(Protocol):
    @property
    def side(self) -> OrderSide: ...


class IStrategyService(ABC):
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
        self._open_direction = direction

    async def on_stop(self) -> None:
        self._is_running = False

    @abstractmethod
    async def on_bar_completed(self, bar: dict) -> Signal | None: ...

    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        pass

    async def on_order_rejected(self, reason: str) -> None:
        return None
