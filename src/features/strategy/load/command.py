"""Load strategy command definition."""

from pathlib import Path

from pydantic import BaseModel, Field

from src.domain.strategy.value_objects import StrategyConfig


class LoadStrategyCommand(BaseModel):
    """Load a strategy from configuration."""

    model_config = {"arbitrary_types_allowed": True}

    config: StrategyConfig | None = None
    path: Path | None = Field(default=None, description="Alternative: load from file")
