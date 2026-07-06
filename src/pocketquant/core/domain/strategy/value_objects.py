from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.domain.strategy.enums import Direction


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: Direction
    confidence: float  # 0.0 - 1.0
    timestamp: datetime
    subscription_id: str
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    entry_logic: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

    @property
    def is_entry(self) -> bool:
        return self.direction in (Direction.LONG, Direction.SHORT)

    @property
    def is_exit(self) -> bool:
        return self.direction == Direction.EXIT


@dataclass
class StopLossConfig:
    enabled: bool = True
    distance_percent: float = 0.01  # 1% default


@dataclass
class TakeProfitConfig:
    enabled: bool = True
    distance_percent: float = 0.02  # 2% default


@dataclass
class OrderConfig:
    """Order execution configuration."""

    entry_type: Literal["market", "limit"] = "market"
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = field(default_factory=TakeProfitConfig)


@dataclass
class StrategyConfig:
    """Strategy configuration loaded from YAML.

    Example YAML:
        id: hitnrun2-btc-1m
        name: "HitNRun2 BTC/USDT"
        symbol: BTCUSDT:BINANCE   # composite {code}:{exchange}
        interval: 1m
        trigger: bar
        broker: paper
        parameters:
          entry_lookback_bars: 240
          sl_lookback_bars: 480
          tp_lookback_bars: 60
          max_loss_pct: 0.01
          min_profit_pct: 0.02
          direction: both
        risk:
          model: percent_risk
          risk_per_trade: 0.02
    """

    id: str
    name: str
    symbol: str
    interval: str
    trigger: Literal["bar", "tick"] = "bar"
    broker: str = "paper"
    parameters: dict = field(default_factory=dict)
    risk: RiskConfig = field(default_factory=RiskConfig)
    orders: OrderConfig = field(default_factory=OrderConfig)
    enabled: bool = True

    def validate(self) -> list[str]:
        errors = []
        if not self.id:
            errors.append("Strategy id is required")
        if not self.name:
            errors.append("Strategy name is required")
        if not self.symbol:
            errors.append("Symbol is required")
        if not self.interval:
            errors.append("Interval is required")
        if self.trigger not in ("bar", "tick"):
            errors.append(f"Invalid trigger: {self.trigger}")
        return errors
