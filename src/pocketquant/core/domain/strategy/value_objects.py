from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec


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
    entry_type: Literal["market", "stop"] = "market"

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")
        if self.entry_type == "stop" and (
            self.entry_price is None or self.direction not in (Direction.LONG, Direction.SHORT)
        ):
            raise ValueError("a stop entry needs entry_price and a LONG or SHORT direction")


@dataclass
class StrategyConfig:
    id: str
    name: str
    symbol: str
    # Ascending; intervals[0] is the entry interval the strategy decides on.
    intervals: list[str]
    broker: str = "paper"
    parameters: dict = field(default_factory=dict)
    risk: RiskConfig = field(default_factory=RiskConfig)
    contract_spec: ContractSpec = LINEAR_SPEC
