from dataclasses import dataclass

from pocketquant.core.domain.risk.services.position_calculator_domain_service import (
    PositionCalculatorDomainService,
)


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = PositionCalculatorDomainService.RISK_PER_TRADE
    max_exposure_percent: float = PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT
    # Account leverage: the exposure cap scales with it. 1.0 is unleveraged.
    leverage: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= 0.10:
            raise ValueError(f"risk_per_trade must be 0-10%, got {self.risk_per_trade:.1%}")
        if not 0 < self.max_exposure_percent <= 1.0:
            raise ValueError(
                f"max_exposure_percent must be 0-100%, got {self.max_exposure_percent:.1%}"
            )
        if self.leverage < 1:
            raise ValueError(f"leverage must be >= 1, got {self.leverage}")
