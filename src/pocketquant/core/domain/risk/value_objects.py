from dataclasses import dataclass

from pocketquant.core.domain.risk.enums import RiskModel
from pocketquant.core.domain.risk.services.position_calculator_domain_service import (
    PositionCalculatorDomainService,
)


@dataclass(frozen=True)
class RiskConfig:
    model: RiskModel = RiskModel.PERCENT_RISK
    risk_per_trade: float = PositionCalculatorDomainService.RISK_PER_TRADE
    max_positions: int = 3
    max_exposure_percent: float = PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= 0.10:
            raise ValueError(f"risk_per_trade must be 0-10%, got {self.risk_per_trade:.1%}")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if not 0 < self.max_exposure_percent <= 1.0:
            raise ValueError(
                f"max_exposure_percent must be 0-100%, got {self.max_exposure_percent:.1%}"
            )
