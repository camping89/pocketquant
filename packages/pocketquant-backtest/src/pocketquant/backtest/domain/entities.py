"""Backtest entities — persisted results with MongoDB persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pocketquant.backtest.domain.value_objects import (
    BacktestMetrics,
    EquityPoint,
    OpenLot,
    OptimizationResultEntry,
)


@dataclass
class BacktestResult:
    """Slim backtest run record — metrics + equity curve + open-lot snapshots.

    After Phase 4 of the storage refactor, fills go to ``backtest_orders.fills[]``
    and round-trip outcomes go to ``backtest_trades``. ``open_positions`` carries
    the still-open lots at run-end so the run doc remains self-contained for
    quick UI snapshots without a cross-collection join.
    """

    id: str
    strategy_code: str
    config_snapshot: dict[str, Any]  # Serialized BacktestConfig
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    started_at: datetime
    completed_at: datetime
    status: str  # "completed", "failed"
    error_message: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)  # For optimizer
    open_positions: list[OpenLot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Alias for API serialization."""
        return self.to_mongo()

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to a slim ``backtest_runs`` document."""
        return {
            "_id": self.id,
            "strategy_code": self.strategy_code,
            "config_snapshot": self.config_snapshot,
            "metrics": self.metrics.to_mongo(),
            "equity_curve": [p.to_mongo() for p in self.equity_curve],
            "open_positions": [p.to_mongo() for p in self.open_positions],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "error_message": self.error_message,
            "parameters": self.parameters,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> BacktestResult:
        """Create from MongoDB document. Tolerates pre-migration shape (ignores legacy keys)."""
        return cls(
            id=data["_id"],
            strategy_code=data["strategy_code"],
            config_snapshot=data["config_snapshot"],
            metrics=BacktestMetrics.from_mongo(data["metrics"]),
            equity_curve=[EquityPoint.from_mongo(p) for p in data.get("equity_curve", [])],
            open_positions=[OpenLot.from_mongo(p) for p in data.get("open_positions", [])],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            status=data["status"],
            error_message=data.get("error_message"),
            parameters=data.get("parameters", {}),
        )


@dataclass
class OptimizationResult:
    """Complete result of a grid optimization run."""

    id: str
    strategy_code: str
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
        """Alias for API serialization."""
        return self.to_mongo()

    def to_mongo(self) -> dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "_id": self.id,
            "strategy_code": self.strategy_code,
            "config_snapshot": self.config_snapshot,
            "target_metric": self.target_metric,
            "total_combinations": self.total_combinations,
            "completed_combinations": self.completed_combinations,
            "failed_combinations": self.failed_combinations,
            "results": [r.to_mongo() for r in self.results],
            "best_parameters": self.best_parameters,
            "best_metrics": self.best_metrics.to_mongo(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "error_message": self.error_message,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> OptimizationResult:
        """Create from MongoDB document."""
        return cls(
            id=data["_id"],
            strategy_code=data["strategy_code"],
            config_snapshot=data["config_snapshot"],
            target_metric=data["target_metric"],
            total_combinations=data["total_combinations"],
            completed_combinations=data["completed_combinations"],
            failed_combinations=data["failed_combinations"],
            results=[OptimizationResultEntry.from_mongo(r) for r in data.get("results", [])],
            best_parameters=data["best_parameters"],
            best_metrics=BacktestMetrics.from_mongo(data["best_metrics"]),
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            status=data["status"],
            error_message=data.get("error_message"),
        )
