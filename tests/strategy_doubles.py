from __future__ import annotations

import dataclasses
from typing import ClassVar

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
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
    # Per-bar overrides of the LONG signal; None skips a bar. A backtest builds its own
    # instance, so a test sets the script on the class with monkeypatch, which restores
    # it after the test. A test that holds the instance may set `script` on it instead.
    SCRIPT: ClassVar[tuple[dict | None, ...] | None] = None

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.min_bars = int((config.parameters or {}).get("min_bars", 0))
        if self.min_bars < 0:
            raise ValueError(f"min_bars must be >= 0, got {self.min_bars}")
        self.bars: list[dict] = []
        self.script: list[dict | None] | None = None if self.SCRIPT is None else list(self.SCRIPT)
        # Per-bar snapshots, set on the loaded instance; None once used up.
        self.snapshots: list[dict | None] | None = None

    async def on_start(self) -> None:
        await super().on_start()
        self.bars.clear()
        self._open_direction = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        self.bars.append(bar)
        if self.snapshots is not None:
            self.snapshot = self.snapshots.pop(0) if self.snapshots else None
        if self.script is not None:
            item = self.script.pop(0) if self.script else None
            if item is None:
                return None
            return dataclasses.replace(self._long(bar), **item)
        if len(self.bars) <= self.min_bars or self._open_direction is not None:
            return None
        self._open_direction = Direction.LONG
        return self._long(bar)

    def _long(self, bar: dict) -> Signal:
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


class NoStoredBars:
    async def find(self, *args: object, **kwargs: object) -> list[Bar]:
        return []


class Continuous24x7CalendarFactory:
    async def for_symbol(self, symbol: str) -> ITradingCalendarPort:
        return Continuous24x7Calendar()
