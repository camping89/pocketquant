"""OptimizationResultEntry VO — one parameter combination's outcome in a grid search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pocketquant.backtest.domain.value_objects.metrics import BacktestMetrics


@dataclass
class OptimizationResultEntry:
    """Single entry in optimization results — one parameter combination."""

    parameters: dict[str, Any]
    metrics: BacktestMetrics
    backtest_id: str
    rank: int  # 1 = best

    def to_mongo(self) -> dict[str, Any]:
        return {
            "parameters": self.parameters,
            "metrics": self.metrics.to_mongo(),
            "backtest_id": self.backtest_id,
            "rank": self.rank,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> OptimizationResultEntry:
        return cls(
            parameters=data["parameters"],
            metrics=BacktestMetrics.from_mongo(data["metrics"]),
            backtest_id=data["backtest_id"],
            rank=data["rank"],
        )
