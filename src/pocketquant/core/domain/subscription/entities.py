from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pocketquant.core.common.exceptions import DomainError
from pocketquant.core.common.uuid import UUID
from pocketquant.core.domain.shared.enums import Interval

# Control-plane run-state: desired = what a human/handler wants, actual = the
# reconcile loop's mirror of RAM truth. Two values only (YAGNI); widen later.
RunState = Literal["running", "stopped"]
ManualAction = Literal["close", "cancel"]
BROKERS = ("paper", "exness")


# Carries the code, symbol and intervals key, not the id: ids are random uuid7, so only
# those say which subscription collided. HTTP 409: a duplicate is a conflict, not a
# malformed request.
class SubscriptionAlreadyExistsError(DomainError):
    def __init__(self, strategy_code: str, symbol: str, intervals_key: str) -> None:
        super().__init__(
            f"Subscription for '{strategy_code}' on '{symbol}' @ '{intervals_key}' already exists.",
            error_code="SUBSCRIPTION_ALREADY_EXISTS",
            status_code=409,
        )


# Uniqueness is the DB index on (strategy_code, symbol, intervals_key), where the key is
# the comma-joined intervals written by to_mongo; the id plays no part.
@dataclass(frozen=True)
class Subscription:
    id: UUID
    strategy_code: str
    symbol: str
    intervals: tuple[Interval, ...]
    created_at: datetime
    desired_state: RunState = "stopped"
    actual_state: RunState = "stopped"
    broker: str = "paper"
    parameters: dict = field(default_factory=dict)
    # A close or cancel the owner asked for, until the lease holder attempts it; the
    # outcome of the last attempt is {action, outcome, at}.
    manual_action: ManualAction | None = None
    manual_action_outcome: dict | None = None

    def to_mongo(self) -> dict:
        return {
            "_id": str(self.id),
            "strategy_code": self.strategy_code,
            "symbol": self.symbol,
            "intervals": [i.value for i in self.intervals],
            "intervals_key": ",".join(i.value for i in self.intervals),
            "parameters": dict(self.parameters),
            "created_at": self.created_at,
            "desired_state": self.desired_state,
            "actual_state": self.actual_state,
            "broker": self.broker,
            "manual_action": self.manual_action,
            "manual_action_outcome": self.manual_action_outcome,
        }

    @classmethod
    def from_mongo(cls, doc: dict) -> Subscription:
        # .get default tolerates docs lacking the control-plane state fields;
        # a missing state reads as "stopped" rather than crashing the load.
        # A missing broker reads as paper; any other stored value fails the load,
        # so a hand-written document can never select an unknown broker.
        broker = doc.get("broker", "paper")
        if broker not in BROKERS:
            raise ValueError(f"unknown broker {broker!r}")
        return cls(
            id=UUID(str(doc["_id"])),
            strategy_code=doc["strategy_code"],
            symbol=doc["symbol"],
            intervals=tuple(Interval(i) for i in doc["intervals"]),
            created_at=doc["created_at"],
            desired_state=doc.get("desired_state", "stopped"),
            actual_state=doc.get("actual_state", "stopped"),
            broker=broker,
            parameters=dict(doc["parameters"]),
            manual_action=doc.get("manual_action"),
            manual_action_outcome=doc.get("manual_action_outcome"),
        )
