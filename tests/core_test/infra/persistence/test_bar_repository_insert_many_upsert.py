"""Unit tests for BarRepository.insert_many — upsert-loop semantics.

Covers:
- insert_many calls upsert_bar exactly once per record, forwarding source kwarg.
- Empty list returns 0 without invoking upsert_bar.
- Missing source kwarg raises TypeError.
- Loop continues past individual upsert failures (logs error, increments only on success).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import (
    _BAR_VALUE_CACHE,
    BarRepository,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    _BAR_VALUE_CACHE.clear()
    yield
    _BAR_VALUE_CACHE.clear()


def _bars(n: int) -> list[Bar]:
    return [
        Bar(
            symbol="BTCUSDT",
            interval=Interval.MINUTE_1,
            datetime=datetime(2026, 1, 1, 0, i, tzinfo=UTC),
            open=1.0 + i,
            high=2.0 + i,
            low=0.5 + i,
            close=1.5 + i,
            volume=100.0,
            tick_count=1,
        )
        for i in range(n)
    ]


def _make_repo() -> BarRepository:
    db = MagicMock()
    db.get_collection.return_value = MagicMock()
    return BarRepository(db)


class TestInsertManyLoop:
    @pytest.mark.asyncio
    async def test_calls_upsert_per_bar_with_same_source(self) -> None:
        repo = _make_repo()
        repo.upsert_bar = AsyncMock()
        records = _bars(3)

        count = await repo.insert_many(records, source="rest_sync_1m")

        assert count == 3
        assert repo.upsert_bar.await_count == 3
        for call in repo.upsert_bar.await_args_list:
            assert call.kwargs.get("source") == "rest_sync_1m"

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self) -> None:
        repo = _make_repo()
        repo.upsert_bar = AsyncMock()
        count = await repo.insert_many([], source="rest_sync_1m")
        assert count == 0
        repo.upsert_bar.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_source_raises_type_error(self) -> None:
        repo = _make_repo()
        with pytest.raises(TypeError):
            await repo.insert_many(_bars(1))  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_continues_on_individual_failure(self) -> None:
        repo = _make_repo()
        # 2nd bar raises; loop must not abort.
        call_log: list[Bar] = []

        async def flaky_upsert(bar: Bar, *, source: str) -> None:  # noqa: ARG001
            call_log.append(bar)
            if len(call_log) == 2:
                raise RuntimeError("boom")

        repo.upsert_bar = flaky_upsert  # type: ignore[assignment]
        records = _bars(3)

        count = await repo.insert_many(records, source="rest_sync_1m")
        assert len(call_log) == 3  # all attempted
        assert count == 2  # 2 succeeded
