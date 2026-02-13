"""Get strategy query definition."""

from dataclasses import dataclass


@dataclass
class GetStrategyQuery:
    """Get a specific strategy by ID."""

    strategy_id: str
