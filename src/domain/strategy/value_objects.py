"""Strategy value objects - Signal, Direction, StrategyConfig."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.domain.risk import RiskConfig, RiskModel


class Direction(Enum):
    """Trading direction for signals."""

    LONG = "long"
    SHORT = "short"
    EXIT = "exit"
    FLAT = "flat"


class Signal(BaseModel):
    """Immutable trading signal from a strategy.

    Represents a trade intention before risk validation and sizing.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    direction: Direction
    confidence: float  # 0.0 - 1.0
    timestamp: datetime
    strategy_id: str
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    entry_logic: str = ""

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {v}")
        return v

    @property
    def is_entry(self) -> bool:
        """Check if signal is an entry (long or short)."""
        return self.direction in (Direction.LONG, Direction.SHORT)

    @property
    def is_exit(self) -> bool:
        """Check if signal is an exit."""
        return self.direction == Direction.EXIT


@dataclass
class StopLossConfig:
    """Stop loss configuration."""

    enabled: bool = True
    distance_percent: float = 0.01  # 1% default


@dataclass
class TakeProfitConfig:
    """Take profit configuration."""

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
        id: ma-cross-btc-5m
        name: "MA Crossover BTC/USDT"
        symbol: BTCUSDT
        exchange: OKX
        interval: 5m
        trigger: bar
        broker: paper
        parameters:
          fast_period: 10
          slow_period: 20
        risk:
          model: percent_risk
          risk_per_trade: 0.02
    """

    id: str
    name: str
    symbol: str
    exchange: str
    interval: str
    trigger: Literal["bar", "tick"] = "bar"
    broker: str = "paper"
    parameters: dict = field(default_factory=dict)
    risk: RiskConfig = field(default_factory=RiskConfig)
    orders: OrderConfig = field(default_factory=OrderConfig)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> StrategyConfig:
        """Create StrategyConfig from dictionary (parsed YAML)."""
        # Parse risk config
        risk_data = data.get("risk", {})
        risk_model = risk_data.get("model", "percent_risk")
        risk_config = RiskConfig(
            model=RiskModel(risk_model) if risk_model else RiskModel.PERCENT_RISK,
            risk_per_trade=risk_data.get("risk_per_trade", 0.02),
            max_positions=risk_data.get("max_positions", 3),
            max_exposure_percent=risk_data.get("max_exposure_percent", 0.10),
        )

        # Parse order config
        orders_data = data.get("orders", {})
        sl_data = orders_data.get("stop_loss", {})
        tp_data = orders_data.get("take_profit", {})
        order_config = OrderConfig(
            entry_type=orders_data.get("entry_type", "market"),
            stop_loss=StopLossConfig(
                enabled=sl_data.get("enabled", True),
                distance_percent=sl_data.get("distance_percent", 0.01),
            ),
            take_profit=TakeProfitConfig(
                enabled=tp_data.get("enabled", True),
                distance_percent=tp_data.get("distance_percent", 0.02),
            ),
        )

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", ""),
            interval=data.get("interval", ""),
            trigger=data.get("trigger", "bar"),
            broker=data.get("broker", "paper"),
            parameters=data.get("parameters", {}),
            risk=risk_config,
            orders=order_config,
            enabled=data.get("enabled", True),
        )

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.id:
            errors.append("Strategy id is required")
        if not self.name:
            errors.append("Strategy name is required")
        if not self.symbol:
            errors.append("Symbol is required")
        if not self.exchange:
            errors.append("Exchange is required")
        if not self.interval:
            errors.append("Interval is required")
        if self.trigger not in ("bar", "tick"):
            errors.append(f"Invalid trigger: {self.trigger}")
        return errors
