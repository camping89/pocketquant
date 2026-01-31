"""Strategy command definitions."""

from dataclasses import dataclass
from pathlib import Path

from src.features.strategy.base import StrategyConfig


@dataclass
class LoadStrategyCommand:
    """Load a strategy from configuration."""

    config: StrategyConfig | None = None
    path: Path | None = None  # Alternative: load from file


@dataclass
class StartStrategyCommand:
    """Start a loaded strategy."""

    strategy_id: str


@dataclass
class StopStrategyCommand:
    """Stop a running strategy."""

    strategy_id: str
