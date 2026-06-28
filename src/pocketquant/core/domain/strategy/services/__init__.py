from pocketquant.core.domain.strategy.services.hitnrun2 import HitNRun2Strategy

STRATEGY_REGISTRY: dict[str, type] = {
    "hitnrun2": HitNRun2Strategy,
}

__all__ = ["HitNRun2Strategy", "STRATEGY_REGISTRY"]
