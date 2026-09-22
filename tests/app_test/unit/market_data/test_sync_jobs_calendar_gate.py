"""The REST sync job does not call a provider for a market that is shut.

Fetching out of hours spends provider rate limit on an empty answer and then
records a no-progress streak for a symbol that is behaving correctly. One
interval of grace after the close keeps the session's final bar reachable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.app_services.sync_jobs import _sync_by_intervals

SYMBOL = "ES1!:CME_MINI"


class _ClosedSince(Continuous24x7Calendar):
    """Shut, having last closed ``ago`` before now."""

    def __init__(self, ago: timedelta) -> None:
        self._ago = ago

    def is_open(self, instant: datetime) -> bool:
        return False

    def previous_close(self, instant: datetime) -> datetime:
        return instant - self._ago


async def _run(calendar) -> tuple[MagicMock, MagicMock]:
    sync_service = MagicMock()
    sync_service.sync_one = AsyncMock()

    tracked = MagicMock()
    tracked.symbol = SYMBOL
    tracked_repo = MagicMock()
    tracked_repo.list_all = AsyncMock(return_value=[tracked])

    history_repo = MagicMock()
    history_repo.record_detail = AsyncMock()

    factory = MagicMock()
    factory.for_symbol = AsyncMock(return_value=calendar)

    await _sync_by_intervals(
        [Interval.MINUTE_1],
        100,
        "sync_1m",
        sync_service,
        tracked_repo,
        history_repo,
        "doc-1",
        source="test",
        calendar_factory=factory,
    )
    return sync_service, history_repo


@pytest.mark.asyncio
async def test_a_long_closed_market_is_not_fetched_at_all() -> None:
    sync_service, history_repo = await _run(_ClosedSince(timedelta(hours=8)))

    sync_service.sync_one.assert_not_awaited()
    detail = history_repo.record_detail.await_args.kwargs
    assert detail["status"] == "skipped"
    assert detail["error"] == "closed"


@pytest.mark.asyncio
async def test_a_market_just_closed_is_still_fetched_once() -> None:
    """Within one interval of the close, the final bar is still reachable."""
    sync_service, _ = await _run(_ClosedSince(timedelta(seconds=30)))

    sync_service.sync_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_open_market_is_always_fetched() -> None:
    sync_service, history_repo = await _run(Continuous24x7Calendar())

    sync_service.sync_one.assert_awaited_once()
    assert all(
        call.kwargs.get("status") != "skipped"
        for call in history_repo.record_detail.await_args_list
    )
