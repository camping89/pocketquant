"""Get strategy template query definition."""

from dataclasses import dataclass


@dataclass
class GetStrategyQuery:
    """Get template metadata for a specific strategy code."""

    strategy_code: str
