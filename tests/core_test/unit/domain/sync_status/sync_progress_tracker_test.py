"""Unit tests for SyncProgressTrackerDomainService — the binary reset-vs-bump rule.

Pure logic, no DB. Pins: inserted_count > 0 → RESET; inserted_count == 0 → BUMP.
No tri-state (had_existing/no_existing) — those branches must not exist.
"""

from __future__ import annotations

import pytest

from pocketquant.core.domain.sync_status.services import (
    SyncProgressDecision,
    SyncProgressTrackerDomainService,
)


@pytest.mark.parametrize("inserted_count", [1, 2, 48, 1000])
def test_positive_insert_resets(inserted_count: int) -> None:
    assert SyncProgressTrackerDomainService.decide(inserted_count) is SyncProgressDecision.RESET


def test_zero_insert_bumps() -> None:
    assert SyncProgressTrackerDomainService.decide(0) is SyncProgressDecision.BUMP


def test_decision_is_binary_only() -> None:
    """Exactly two outcomes — guards against a fabricated tri-state."""
    assert set(SyncProgressDecision) == {
        SyncProgressDecision.RESET,
        SyncProgressDecision.BUMP,
    }
