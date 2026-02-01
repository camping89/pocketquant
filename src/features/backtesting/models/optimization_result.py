"""Optimization result models for grid search results."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.features.backtesting.models.backtest_result import BacktestMetrics


@dataclass
class OptimizationResultEntry:
    """Single entry in optimization results - one parameter combination."""

    parameters: dict[str, Any]
    metrics: BacktestMetrics
    backtest_id: str
    rank: int  # 1 = best

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": self.parameters,
            "metrics": self.metrics.to_dict(),
            "backtest_id": self.backtest_id,
            "rank": self.rank,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OptimizationResultEntry":
        return cls(
            parameters=data["parameters"],
            metrics=BacktestMetrics.from_dict(data["metrics"]),
            backtest_id=data["backtest_id"],
            rank=data["rank"],
        )


@dataclass
class OptimizationResult:
    """Complete result of a grid optimization run."""

    id: str
    strategy_id: str
    config_snapshot: dict[str, Any]  # Serialized OptimizationConfig
    target_metric: str
    total_combinations: int
    completed_combinations: int
    failed_combinations: int
    results: list[OptimizationResultEntry]  # Ranked by target metric
    best_parameters: dict[str, Any]
    best_metrics: BacktestMetrics
    started_at: datetime
    completed_at: datetime
    status: str  # "running", "completed", "failed"
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "_id": self.id,
            "strategy_id": self.strategy_id,
            "config_snapshot": self.config_snapshot,
            "target_metric": self.target_metric,
            "total_combinations": self.total_combinations,
            "completed_combinations": self.completed_combinations,
            "failed_combinations": self.failed_combinations,
            "results": [r.to_dict() for r in self.results],
            "best_parameters": self.best_parameters,
            "best_metrics": self.best_metrics.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OptimizationResult":
        """Create from MongoDB document."""
        return cls(
            id=data["_id"],
            strategy_id=data["strategy_id"],
            config_snapshot=data["config_snapshot"],
            target_metric=data["target_metric"],
            total_combinations=data["total_combinations"],
            completed_combinations=data["completed_combinations"],
            failed_combinations=data["failed_combinations"],
            results=[OptimizationResultEntry.from_dict(r) for r in data.get("results", [])],
            best_parameters=data["best_parameters"],
            best_metrics=BacktestMetrics.from_dict(data["best_metrics"]),
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            status=data["status"],
            error_message=data.get("error_message"),
        )
