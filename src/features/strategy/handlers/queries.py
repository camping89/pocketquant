"""Strategy query definitions."""

from dataclasses import dataclass


@dataclass
class GetStrategiesQuery:
    """Get all loaded strategies."""

    pass


@dataclass
class GetStrategyQuery:
    """Get a specific strategy by ID."""

    strategy_id: str
