"""Risk value objects - RiskConfig."""

from dataclasses import dataclass

from src.domain.concepts.risk.enums import RiskModel


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
        if not 0 < self.risk_per_trade <= 0.10:
            raise ValueError(f"risk_per_trade must be 0-10%, got {self.risk_per_trade:.1%}")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if not 0 < self.max_exposure_percent <= 1.0:
            raise ValueError(
                f"max_exposure_percent must be 0-100%, got {self.max_exposure_percent:.1%}"
            )
