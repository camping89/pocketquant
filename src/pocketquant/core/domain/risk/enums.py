from enum import Enum


class RiskModel(Enum):
    PERCENT_RISK = "percent_risk"  # Fixed % of account per trade
    KELLY = "kelly"  # Kelly criterion
    FIXED = "fixed"  # Fixed size per trade
