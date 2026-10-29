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
    assert set(SyncProgressDecision) == {
        SyncProgressDecision.RESET,
        SyncProgressDecision.BUMP,
    }
