"""Risk value objects - RiskConfig and RiskModel."""

from dataclasses import dataclass
from enum import Enum


class RiskModel(Enum):
    """Position sizing model selection."""

    PERCENT_RISK = "percent_risk"  # Fixed % of account per trade
    KELLY = "kelly"  # Kelly criterion
    FIXED = "fixed"  # Fixed size per trade


@dataclass(frozen=True)
class RiskConfig:
    """Risk configuration for a strategy.

    Loaded from YAML, validated at strategy load time.
    """

    model: RiskModel = RiskModel.PERCENT_RISK
    risk_per_trade: float = 0.02  # 2% default per validation
    max_positions: int = 3
    max_exposure_percent: float = 0.10  # 10% max portfolio exposure

    def __post_init__(self) -> None:
        """Validate risk parameters."""
        if not 0 < self.risk_per_trade <= 0.10:
            raise ValueError(
                f"risk_per_trade must be 0-10%, got {self.risk_per_trade:.1%}"
            )
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if not 0 < self.max_exposure_percent <= 1.0:
            raise ValueError(
                f"max_exposure_percent must be 0-100%, got {self.max_exposure_percent:.1%}"
            )
