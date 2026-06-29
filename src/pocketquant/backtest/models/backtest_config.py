from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BacktestConfig:
    """Configuration for a single backtest run.

    Attributes:
        strategy_code: Unique identifier for the strategy to backtest.
        symbol: Composite trading symbol ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
        interval: Bar interval (e.g., "5m", "1h", "1d").
        start_date: Start datetime for historical replay (minute precision).
        end_date: End datetime for historical replay (minute precision).
        initial_capital: Starting capital for the backtest.
        slippage_bps: Slippage in basis points (10 = 0.1%).
        commission_bps: Commission in basis points (10 = 0.1%).
        replay_speed: Replay speed multiplier (0 = max speed).
        parameters: Strategy-specific parameters for optimization.
    """

    strategy_code: str
    symbol: str
    interval: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10_000.0
    slippage_bps: float = 10.0  # 0.1% default
    commission_bps: float = 10.0  # 0.1% default (validated requirement)
    replay_speed: float = 0.0  # 0 = max speed, 1 = real-time, 10 = 10x
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def slippage_percent(self) -> float:
        return self.slippage_bps / 10_000

    @property
    def commission_percent(self) -> float:
        return self.commission_bps / 10_000
