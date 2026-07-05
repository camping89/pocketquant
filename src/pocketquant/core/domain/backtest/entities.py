from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pocketquant.core.domain.backtest.value_objects import OpenLot
from pocketquant.core.domain.trading import EquityPoint, PerformanceMetrics


@dataclass
class BacktestResult:
    """Slim backtest run record — metrics + equity curve + open-lot snapshots.

    Storage layout: per-order audit (fills + lifecycle events) lives in
    ``backtest_orders.fills[]`` and round-trip outcomes in ``backtest_trades``.
    ``open_positions`` carries the still-open lots at run-end so the run doc
    remains self-contained for quick UI snapshots without a cross-collection
    join.
    """

    id: UUID
    strategy_code: str
    config_snapshot: dict[str, Any]  # Serialized BacktestConfig
    metrics: PerformanceMetrics
    equity_curve: list[EquityPoint]
    started_at: datetime
    completed_at: datetime
    status: str  # "started", "finished", "failed"
    # Denormalized from config_snapshot so history can scope by (strategy, symbol,
    # interval) with an index. symbol is composite CODE:EXCHANGE (e.g. BTCUSDT:BINANCE).
    symbol: str = ""
    interval: str = ""
    error_message: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)  # For optimizer
    open_positions: list[OpenLot] = field(default_factory=list)
    verdict: str | None = None  # Human-readable conclusion (set post-run via PATCH)

    @classmethod
    def started(cls, run_id: str, config_snapshot: dict[str, Any]) -> BacktestResult:
        """Placeholder doc the route persists before spawning the engine task.

        Zeroed metrics keep ``from_mongo`` round-tripping while FE polls — the
        engine overwrites this same ``run_id`` with the real result on finish.
        ``completed_at`` mirrors ``started_at`` so the slim doc stays well-formed
        until then.
        """
        now = datetime.now(UTC)
        return cls(
            id=UUID(run_id),
            strategy_code=config_snapshot["strategy_code"],
            config_snapshot=config_snapshot,
            metrics=PerformanceMetrics.empty(),
            equity_curve=[],
            started_at=now,
            completed_at=now,
            status="started",
            # Composite CODE:EXCHANGE, uppercased so the history scope filter
            # (which also uppercases) matches without a casing mismatch.
            symbol=config_snapshot.get("symbol", "").upper(),
            interval=config_snapshot.get("interval", ""),
            parameters=config_snapshot.get("parameters", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return self.to_mongo()

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": str(self.id),
            "strategy_code": self.strategy_code,
            "symbol": self.symbol,
            "interval": self.interval,
            "config_snapshot": self.config_snapshot,
            "metrics": self.metrics.to_mongo(),
            "equity_curve": [p.to_mongo() for p in self.equity_curve],
            "open_positions": [p.to_mongo() for p in self.open_positions],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "error_message": self.error_message,
            "parameters": self.parameters,
            "verdict": self.verdict,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> BacktestResult:
        """Create from MongoDB document. Tolerates pre-migration shape (ignores legacy keys)."""
        snapshot = data.get("config_snapshot", {})
        return cls(
            id=UUID(data["_id"]),
            strategy_code=data["strategy_code"],
            config_snapshot=snapshot,
            metrics=PerformanceMetrics.from_mongo(data["metrics"]),
            equity_curve=[EquityPoint.from_mongo(p) for p in data.get("equity_curve", [])],
            open_positions=[OpenLot.from_mongo(p) for p in data.get("open_positions", [])],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            status=data["status"],
            # Pre-denormalization docs lack top-level symbol/interval — fall back
            # to the config snapshot; empty string if even that is absent. Uppercase
            # keeps it consistent with the scope filter's normalization.
            symbol=(data.get("symbol") or snapshot.get("symbol", "")).upper(),
            interval=data.get("interval") or snapshot.get("interval", ""),
            error_message=data.get("error_message"),
            parameters=data.get("parameters", {}),
            verdict=data.get("verdict"),
        )
