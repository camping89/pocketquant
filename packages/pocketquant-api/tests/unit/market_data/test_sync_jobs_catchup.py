"""Unit tests for enqueue_missed_catchups — pure decision logic, mocked deps.

Catches the three catch-up branches:
  - no history yet (fresh DB) → skip (don't fire on first deploy)
  - recent success (within threshold) → skip
  - stale success (gap > max_gap) → enqueue `<job_id>_catchup` one-off
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from pocketquant.api.market_data.app_services.sync_jobs import (
    CATCHUP_TARGETS,
    enqueue_missed_catchups,
)


async def test_catchup_skips_when_no_history() -> None:
    """Fresh DB → no last success → no catch-up enqueued."""
    repo = MagicMock()
    repo.get_last_successful_started_at = AsyncMock(return_value=None)
    scheduler = MagicMock()

    await enqueue_missed_catchups(repo, scheduler)

    scheduler.add_one_off_job.assert_not_called()


async def test_catchup_skips_when_recent() -> None:
    """Last success 1h ago → all thresholds are >1h → no catch-up."""
    repo = MagicMock()
    repo.get_last_successful_started_at = AsyncMock(
        return_value=datetime.now(UTC) - timedelta(hours=1)
    )
    scheduler = MagicMock()

    await enqueue_missed_catchups(repo, scheduler)

    scheduler.add_one_off_job.assert_not_called()


async def test_catchup_enqueues_when_stale() -> None:
    """All targets stale (>26h since success) → one-off enqueued for each."""
    repo = MagicMock()
    # 30h gap exceeds every CATCHUP_TARGETS max_gap (largest is sync_backfill@25h).
    repo.get_last_successful_started_at = AsyncMock(
        return_value=datetime.now(UTC) - timedelta(hours=30)
    )
    scheduler = MagicMock()

    await enqueue_missed_catchups(repo, scheduler)

    assert scheduler.add_one_off_job.call_count == len(CATCHUP_TARGETS)
    # Verify suffixes — each catch-up uses `<job_id>_catchup` as job_id so
    # replace_existing=True merges duplicate multi-instance dispatches safely.
    enqueued_ids = {
        c.kwargs.get("job_id") for c in scheduler.add_one_off_job.call_args_list
    }
    assert enqueued_ids == {f"{job_id}_catchup" for job_id, _, _ in CATCHUP_TARGETS}


async def test_catchup_partial_stale_only_enqueues_stale_ones() -> None:
    """Mixed gaps: sync_repair stale (>12.5h), others fresh → only repair fires."""
    now = datetime.now(UTC)

    async def last_success(job_id: str) -> datetime | None:
        if job_id == "sync_repair":
            return now - timedelta(hours=13)  # > 12.5h threshold
        return now - timedelta(hours=2)  # well within 25h threshold

    repo = MagicMock()
    repo.get_last_successful_started_at = AsyncMock(side_effect=last_success)
    scheduler = MagicMock()

    await enqueue_missed_catchups(repo, scheduler)

    assert scheduler.add_one_off_job.call_count == 1
    call = scheduler.add_one_off_job.call_args
    assert call.kwargs.get("job_id") == "sync_repair_catchup"
