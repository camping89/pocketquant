"""Subscription — runtime mapping of a strategy template to a market symbol/interval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pocketquant.core.common.exceptions import DomainError
from pocketquant.core.domain.shared.enums import Interval

# Control-plane run-state: desired = what a human/handler wants, actual = the
# reconcile loop's mirror of RAM truth. Two values only (YAGNI); widen later.
RunState = Literal["running", "stopped"]


class SubscriptionAlreadyExistsError(DomainError):
    """Raised when a subscription with the same deterministic ID already exists."""

    def __init__(self, sub_id: str) -> None:
        super().__init__(
            f"Subscription '{sub_id}' already exists.",
            error_code="SUBSCRIPTION_ALREADY_EXISTS",
        )


@dataclass(frozen=True)
class Subscription:
    """Immutable runtime mapping of a strategy template to a (symbol, interval) pair.

    ``symbol`` stores composite identifier ``{code}:{exchange}``.

    The ID is deterministic — derived from the 3-tuple — so the same subscription
    cannot be inserted twice, and the ID is stable in URLs and cache keys.
    """

    id: str
    strategy_code: str
    symbol: str
    interval: Interval
    created_at: datetime
    desired_state: RunState = "stopped"
    actual_state: RunState = "stopped"

    @staticmethod
    def deterministic_id(
        strategy_code: str,
        symbol: str,
        interval: str | Interval,
    ) -> str:
        """Return 16 lowercase hex chars derived from sha256 of the 3-tuple.

        Inputs are normalized: symbol uppercased, interval as its string value
        so the result is stable regardless of how callers pass it.

        Hash stability: the hash input is the *value* of ``strategy_code``
        (e.g. ``"hitnrun2"``), not the parameter name. Renaming this parameter
        does NOT change existing PKs. Do not "improve" the hash formula —
        existing subscription IDs in production depend on this exact recipe.
        """
        interval_val = interval.value if isinstance(interval, Interval) else str(interval)
        raw = f"{strategy_code}|{symbol.upper()}|{interval_val}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_mongo(self) -> dict:
        return {
            "_id": self.id,
            "strategy_code": self.strategy_code,
            "symbol": self.symbol,
            "interval": self.interval.value,
            "created_at": self.created_at,
            "desired_state": self.desired_state,
            "actual_state": self.actual_state,
        }

    @classmethod
    def from_mongo(cls, doc: dict) -> Subscription:
        # .get default tolerates legacy docs written before the state fields
        # existed (read may happen before the boot migration backfills them).
        return cls(
            id=doc["_id"],
            strategy_code=doc["strategy_code"],
            symbol=doc["symbol"],
            interval=Interval(doc["interval"]),
            created_at=doc["created_at"],
            desired_state=doc.get("desired_state", "stopped"),
            actual_state=doc.get("actual_state", "stopped"),
        )
