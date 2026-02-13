"""Get strategies operation."""

from src.features.strategy.get_all.handler import GetStrategiesHandler
from src.features.strategy.get_all.query import GetStrategiesQuery

__all__ = [
    "GetStrategiesQuery",
    "GetStrategiesHandler",
]
