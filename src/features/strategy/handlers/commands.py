"""Strategy command definitions."""

from pathlib import Path

from pydantic import BaseModel, Field

from src.features.strategy.base import StrategyConfig


class LoadStrategyCommand(BaseModel):
    """Load a strategy from configuration."""

    model_config = {"arbitrary_types_allowed": True}

    config: StrategyConfig | None = None
    path: Path | None = Field(default=None, description="Alternative: load from file")


class StartStrategyCommand(BaseModel):
    """Start a loaded strategy."""

    strategy_id: str = Field(..., description="Strategy identifier")


class StopStrategyCommand(BaseModel):
    """Stop a running strategy."""

    strategy_id: str = Field(..., description="Strategy identifier")
