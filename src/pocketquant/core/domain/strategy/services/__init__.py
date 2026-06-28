from pocketquant.core.domain.strategy.services.engulfing import EngulfingStrategy
from pocketquant.core.domain.strategy.services.hitnrun2 import HitNRun2Strategy

STRATEGY_REGISTRY: dict[str, type] = {
    "hitnrun2": HitNRun2Strategy,
    "engulfing": EngulfingStrategy,
}

__all__ = ["EngulfingStrategy", "HitNRun2Strategy", "STRATEGY_REGISTRY"]
