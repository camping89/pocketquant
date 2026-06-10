"""Risk enums - position sizing models."""

from enum import Enum


class RiskModel(Enum):
    """Position sizing model selection."""

    PERCENT_RISK = "percent_risk"  # Fixed % of account per trade
    KELLY = "kelly"  # Kelly criterion
    FIXED = "fixed"  # Fixed size per trade
