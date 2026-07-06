from pocketquant.core.domain.strategy.services.engulfing_pullback30_touch_strategy_service import (
    EngulfingPullback30TouchStrategyService,
)
from pocketquant.core.domain.strategy.services.engulfing_strategy_service import (
    EngulfingStrategyService,
)
from pocketquant.core.domain.strategy.services.hitnrun2_strategy_service import (
    HitNRun2StrategyService,
)

STRATEGY_REGISTRY: dict[str, type] = {
    "hitnrun2": HitNRun2StrategyService,
    "engulfing": EngulfingStrategyService,
    "engulfing_pullback30_touch": EngulfingPullback30TouchStrategyService,
}

__all__ = [
    "STRATEGY_REGISTRY",
    "EngulfingPullback30TouchStrategyService",
    "EngulfingStrategyService",
    "HitNRun2StrategyService",
]
