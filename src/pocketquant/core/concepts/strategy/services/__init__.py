"""Strategy services - concrete strategy implementations."""

from pocketquant.core.concepts.strategy.services.hitnrun2 import HitNRun2Strategy

STRATEGY_REGISTRY: dict[str, type] = {
    "hitnrun2": HitNRun2Strategy,
}

__all__ = ["HitNRun2Strategy", "STRATEGY_REGISTRY"]
