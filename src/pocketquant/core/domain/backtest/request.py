from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

BacktestRequestKind = Literal["single", "subscription"]
BacktestRequestStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class BacktestRequest:
    """A queued backtest execution request — Mongo-backed work item.

    Replaces the APScheduler ``bt:*`` one-off jobs. The ``pocketquant-bff``
    gateway INSERTs a ``pending`` request (pure DB write, no scheduler); the
    headless ``pocketquant-app`` worker atomically claims it, dispatches by
    ``kind``, and writes terminal status.

    ``kind == "subscription"``: the worker writes the full result to
    ``backtest_runs`` keyed by ``sub_id`` (existing per-subscription cache);
    ``result`` here stays None — FE polls ``/subscriptions/{id}/backtest``.

    ``kind == "single"``: there is no subscription to key on, so the worker
    embeds the assembled FE response (``run_id``/``status``/``metrics``/
    ``positions``) in ``result`` and FE polls ``/backtest/requests/{id}``.
    """

    id: str
    kind: BacktestRequestKind
    status: BacktestRequestStatus
    requested_at: datetime
    sub_id: str | None = None
    strategy_code: str | None = None
    config: dict[str, Any] | None = None  # serialized BacktestConfig for single kind
    result: dict[str, Any] | None = None  # embedded FE response for single kind when done
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "requested_at": self.requested_at,
            "sub_id": self.sub_id,
            "strategy_code": self.strategy_code,
            "config": self.config,
            "result": self.result,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> BacktestRequest:
        return cls(
            id=data["_id"],
            kind=data["kind"],
            status=data["status"],
            requested_at=data["requested_at"],
            sub_id=data.get("sub_id"),
            strategy_code=data.get("strategy_code"),
            config=data.get("config"),
            result=data.get("result"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )
