"""StrategySubscription — runtime mapping of a strategy to a market symbol/interval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.common.exceptions import DomainError
from pocketquant.core.domain.shared.enums import Interval


class SubscriptionAlreadyExistsError(DomainError):
    """Raised when a subscription with the same deterministic ID already exists."""

    def __init__(self, sub_id: str) -> None:
        super().__init__(
            f"Subscription '{sub_id}' already exists.",
            error_code="SUBSCRIPTION_ALREADY_EXISTS",
        )


@dataclass(frozen=True)
class StrategySubscription:
    """Immutable runtime mapping of a strategy to a (symbol, exchange, interval) tuple.

    The ID is deterministic — derived from the 4-tuple — so the same subscription
    cannot be inserted twice, and the ID is stable in URLs and cache keys.
    """

    id: str
    strategy_id: str
    symbol: str
    exchange: str
    interval: Interval
    created_at: datetime

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def deterministic_id(
        strategy_id: str,
        symbol: str,
        exchange: str,
        interval: str | Interval,
    ) -> str:
        """Return 16 lowercase hex chars derived from sha256 of the 4-tuple.

        Inputs are normalized: symbol and exchange uppercased, interval as its
        string value so the result is stable regardless of how callers pass it.
        """
        interval_val = interval.value if isinstance(interval, Interval) else str(interval)
        raw = f"{strategy_id}|{symbol.upper()}|{exchange.upper()}|{interval_val}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # MongoDB serialisation
    # ------------------------------------------------------------------

    def to_mongo(self) -> dict:
        """Serialise to a MongoDB document. Uses _id = id for dedup by PK."""
        return {
            "_id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict) -> "StrategySubscription":
        """Deserialise from a MongoDB document."""
        return cls(
            id=doc["_id"],
            strategy_id=doc["strategy_id"],
            symbol=doc["symbol"],
            exchange=doc["exchange"],
            interval=Interval(doc["interval"]),
            created_at=doc["created_at"],
        )
