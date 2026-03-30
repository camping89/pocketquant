"""Strategy services - concrete strategy implementations."""

from pocketquant.core.concepts.strategy.services.hit_and_run import HitAndRunStrategy
from pocketquant.core.concepts.strategy.services.ma_crossover import MACrossoverStrategy

# Registry: maps strategy class name (kebab or snake) → IStrategy subclass
STRATEGY_REGISTRY: dict[str, type] = {
    "ma_crossover": MACrossoverStrategy,
    "hit_and_run": HitAndRunStrategy,
}

__all__ = ["MACrossoverStrategy", "HitAndRunStrategy", "STRATEGY_REGISTRY"]
