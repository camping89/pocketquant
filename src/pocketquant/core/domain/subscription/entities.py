from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pocketquant.core.common.exceptions import DomainError
from pocketquant.core.common.uuid import UUID
from pocketquant.core.domain.shared.enums import Interval

# Control-plane run-state: desired = what a human/handler wants, actual = the
# reconcile loop's mirror of RAM truth. Two values only (YAGNI); widen later.
RunState = Literal["running", "stopped"]


class SubscriptionAlreadyExistsError(DomainError):
    """Raised when a subscription for the same (strategy, symbol, interval) exists.

    Carries the triple, not the id: ids are random uuid7, so only the triple
    identifies WHICH subscription collided.
    """

    def __init__(self, strategy_code: str, symbol: str, interval: str) -> None:
        super().__init__(
            f"Subscription for '{strategy_code}' on '{symbol}' @ '{interval}' already exists.",
            error_code="SUBSCRIPTION_ALREADY_EXISTS",
        )


@dataclass(frozen=True)
class Subscription:
    """Immutable runtime mapping of a strategy template to a (symbol, interval) pair.

    ``symbol`` stores composite identifier ``{code}:{exchange}``.

    The ID is a random uuid7 — uniqueness of the (strategy_code, symbol,
    interval) triple is enforced by the DB compound unique index, not the id.
    """

    id: UUID
    strategy_code: str
    symbol: str
    interval: Interval
    created_at: datetime
    desired_state: RunState = "stopped"
    actual_state: RunState = "stopped"

    def to_mongo(self) -> dict:
        return {
            "_id": str(self.id),
            "strategy_code": self.strategy_code,
            "symbol": self.symbol,
            "interval": self.interval.value,
            "created_at": self.created_at,
            "desired_state": self.desired_state,
            "actual_state": self.actual_state,
        }

    @classmethod
    def from_mongo(cls, doc: dict) -> Subscription:
        # .get default tolerates docs lacking the control-plane state fields;
        # a missing state reads as "stopped" rather than crashing the load.
        return cls(
            id=UUID(str(doc["_id"])),
            strategy_code=doc["strategy_code"],
            symbol=doc["symbol"],
            interval=Interval(doc["interval"]),
            created_at=doc["created_at"],
            desired_state=doc.get("desired_state", "stopped"),
            actual_state=doc.get("actual_state", "stopped"),
        )
