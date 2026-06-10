"""Domain rule deciding how a sync outcome updates the empty-fetch streak.

Owns the binary invariant: a sync that persisted at least one new bar made
progress (reset the streak); a sync that persisted none did not (bump it). The
counter itself is an atomic ``$inc``/``$set`` at the persistence boundary — this
service only chooses WHICH op, never reads-then-writes.
"""

from __future__ import annotations

from enum import Enum


class SyncProgressDecision(Enum):
    """Which empty-fetch counter op a sync outcome warrants."""

    RESET = "reset"
    BUMP = "bump"


class SyncProgressTracker:
    """Decides reset-vs-bump from the sync outcome already in hand."""

    @staticmethod
    def decide(inserted_count: int) -> SyncProgressDecision:
        """Reset when new bars were persisted, else bump the empty-fetch streak.

        Binary on ``inserted_count`` — covers empty-fetch, all-misaligned, and
        all-already-existing cases uniformly (all yield ``inserted_count == 0``).
        """
        if inserted_count > 0:
            return SyncProgressDecision.RESET
        return SyncProgressDecision.BUMP
