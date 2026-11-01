from __future__ import annotations

from typing import ClassVar

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


# Signals LONG with a 1% stop and target on every bar after `min_bars` bars while flat.
class ScriptedStrategy(IStrategyService):
    DEFAULTS: ClassVar[dict] = {"min_bars": 0}

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.min_bars = int((config.parameters or {}).get("min_bars", 0))
        if self.min_bars < 0:
            raise ValueError(f"min_bars must be >= 0, got {self.min_bars}")
        self.bars: list[dict] = []

    async def on_start(self) -> None:
        await super().on_start()
        self.bars.clear()
        self._open_direction = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        self.bars.append(bar)
        if len(self.bars) <= self.min_bars or self._open_direction is not None:
            return None
        self._open_direction = Direction.LONG
        close = float(bar["close"])
        return Signal(
            symbol=self.config.symbol,
            direction=Direction.LONG,
            confidence=1.0,
            timestamp=bar["timestamp"],
            subscription_id=self.id,
            entry_price=close,
            stop_loss_price=close * 0.99,
            take_profit_price=close * 1.01,
        )

    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        if self._open_direction == Direction.LONG and order.side == OrderSide.SELL:
            self._open_direction = None

    async def on_order_rejected(self, reason: str) -> None:
        self._open_direction = None
