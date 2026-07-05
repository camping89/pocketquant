from pocketquant.core.domain.strategy.services.engulfing_strategy_service import (
    EngulfingStrategyService,
)
from pocketquant.core.domain.strategy.services.hitnrun2_strategy_service import (
    HitNRun2StrategyService,
)

STRATEGY_REGISTRY: dict[str, type] = {
    "hitnrun2": HitNRun2StrategyService,
    "engulfing": EngulfingStrategyService,
}

__all__ = ["EngulfingStrategyService", "HitNRun2StrategyService", "STRATEGY_REGISTRY"]
