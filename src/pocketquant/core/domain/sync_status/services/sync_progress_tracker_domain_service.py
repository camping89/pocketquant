# Only chooses which op; the counter is an atomic $inc/$set at the persistence
# boundary, never a read-then-write.

from __future__ import annotations

from enum import Enum


class SyncProgressDecision(Enum):
    RESET = "reset"
    BUMP = "bump"


class SyncProgressTrackerDomainService:
    @staticmethod
    def decide(inserted_count: int) -> SyncProgressDecision:
        if inserted_count > 0:
            return SyncProgressDecision.RESET
        return SyncProgressDecision.BUMP
