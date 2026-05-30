"""Tests for filter_new_bars — DB-aware existence filter that fills non-contiguous gaps.

Covers 4 main scenarios (continuous DB, tail gap, middle hole, empty DB)
plus edge cases (empty records, None datetime, log emission, naive-vs-aware
timezone equivalence).

Mocks BarRepository.find_datetimes with AsyncMock; uses structlog testing
context to assert log fields.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import structlog
from pocketquant.api.market_data.handlers.sync.sync_one.bar_filters import (
    filter_new_bars,
)
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval

SYMBOL = "BTCUSDT:BINANCE"


def _bar(ts: datetime) -> Bar:
    return Bar(
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        datetime=ts,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )


def _series(start: datetime, count: int, step_minutes: int = 1) -> list[Bar]:
    return [_bar(start + timedelta(minutes=i * step_minutes)) for i in range(count)]


def _existing_docs(times: list[datetime], naive: bool = True) -> list[dict]:
    """Mock find_datetimes return shape. naive=True mimics tz-naive Mongo storage."""
    return [
        {"_id": f"id-{i}", "datetime": (t.replace(tzinfo=None) if naive else t)}
        for i, t in enumerate(times)
    ]


@pytest.fixture
def bar_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_datetimes = AsyncMock(return_value=[])
    return repo


@pytest.mark.asyncio
async def test_continuous_db_keeps_only_new(bar_repo: AsyncMock) -> None:
    """DB has 99 contiguous bars; fetch 100 covering same range + 1 new tail.

    Expect: 1 new bar kept, 99 existing dropped.
    """
    base = datetime(2026, 5, 7, 2, 0, tzinfo=UTC)
    records = _series(base, 100)
    bar_repo.find_datetimes.return_value = _existing_docs(
        [base + timedelta(minutes=i) for i in range(99)]
    )

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert len(result) == 1
    assert result[0].datetime == base + timedelta(minutes=99)


@pytest.mark.asyncio
async def test_tail_gap_keeps_all_below_latest(bar_repo: AsyncMock) -> None:
    """DB has 3 bars at the end; fetch 5000 covering 3.5 days.

    Expect: 4997 new bars kept (everything except the 3 tail bars).
    """
    tail_base = datetime(2026, 5, 7, 3, 35, tzinfo=UTC)
    fetch_start = tail_base - timedelta(minutes=4997)
    records = _series(fetch_start, 5000)

    tail_existing = [tail_base, tail_base + timedelta(minutes=1), tail_base + timedelta(minutes=2)]
    bar_repo.find_datetimes.return_value = _existing_docs(tail_existing)

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert len(result) == 4997
    kept_dts = {r.datetime for r in result}
    for ex in tail_existing:
        assert ex not in kept_dts


@pytest.mark.asyncio
async def test_middle_hole_keeps_hole_bars(bar_repo: AsyncMock) -> None:
    """DB has 02:00..02:30 + 03:00..03:38; fetch 100 covering 02:00..03:39.

    Hole = 02:31..02:59 (29 bars). Plus 1 new tail bar 03:39.
    Expect: 30 bars kept.
    """
    base = datetime(2026, 5, 7, 2, 0, tzinfo=UTC)
    records = _series(base, 100)  # 02:00..03:39

    span_a = [base + timedelta(minutes=i) for i in range(31)]  # 02:00..02:30
    span_b = [base + timedelta(minutes=60 + i) for i in range(39)]  # 03:00..03:38
    bar_repo.find_datetimes.return_value = _existing_docs(span_a + span_b)

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    kept_dts = {r.datetime for r in result}
    expected_hole = {base + timedelta(minutes=31 + i) for i in range(29)}  # 02:31..02:59
    expected_tail = {base + timedelta(minutes=99)}  # 03:39

    assert len(result) == 30
    assert expected_hole.issubset(kept_dts)
    assert expected_tail.issubset(kept_dts)


@pytest.mark.asyncio
async def test_empty_db_keeps_all(bar_repo: AsyncMock) -> None:
    """DB empty → find_datetimes returns []; all records kept."""
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 100)
    bar_repo.find_datetimes.return_value = []

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert len(result) == 100


@pytest.mark.asyncio
async def test_empty_records_returns_empty(bar_repo: AsyncMock) -> None:
    result = await filter_new_bars([], SYMBOL, Interval.MINUTE_1, bar_repo)
    assert result == []
    bar_repo.find_datetimes.assert_not_called()


@pytest.mark.asyncio
async def test_records_with_none_datetime_passthrough(bar_repo: AsyncMock) -> None:
    """Bars with datetime=None always pass through (downstream handles)."""
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    valid = _bar(base)
    invalid = Bar(
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        datetime=None,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )
    records = [valid, invalid]
    bar_repo.find_datetimes.return_value = _existing_docs([base])  # valid IS existing

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert len(result) == 1
    assert result[0].datetime is None  # only the None-datetime bar survives


@pytest.mark.asyncio
async def test_all_none_datetimes_skip_query(bar_repo: AsyncMock) -> None:
    """If no record has datetime, skip DB query entirely and return as-is."""
    invalid = Bar(
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        datetime=None,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )
    records = [invalid, invalid]

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert result == records
    bar_repo.find_datetimes.assert_not_called()


@pytest.mark.asyncio
async def test_naive_mongo_datetime_matches_aware_record(bar_repo: AsyncMock) -> None:
    """Mongo returns tz-naive; record is tz-aware. coerce_utc must reconcile."""
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 5)
    # Naive return (default behavior of find_datetimes against non-tz-aware client)
    bar_repo.find_datetimes.return_value = _existing_docs(
        [base + timedelta(minutes=i) for i in range(5)],
        naive=True,
    )

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert result == []  # all 5 filtered as existing


@pytest.mark.asyncio
async def test_logs_filtered_existing_when_skipped(bar_repo: AsyncMock) -> None:
    """Verify info log emitted with kept/skipped/existing_count fields."""
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 10)
    bar_repo.find_datetimes.return_value = _existing_docs(
        [base + timedelta(minutes=i) for i in range(7)]
    )

    with structlog.testing.capture_logs() as logs:
        result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert len(result) == 3
    matching = [e for e in logs if e.get("event") == "market_data.sync.filtered_existing"]
    assert len(matching) == 1
    entry = matching[0]
    assert entry["kept"] == 3
    assert entry["skipped"] == 7
    assert entry["existing_count"] == 7


@pytest.mark.asyncio
async def test_no_log_when_nothing_skipped(bar_repo: AsyncMock) -> None:
    """No log emitted when all records are kept (empty DB scenario)."""
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 5)
    bar_repo.find_datetimes.return_value = []

    with structlog.testing.capture_logs() as logs:
        await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    matching = [e for e in logs if e.get("event") == "market_data.sync.filtered_existing"]
    assert matching == []


@pytest.mark.asyncio
async def test_query_uses_min_max_of_record_datetimes(bar_repo: AsyncMock) -> None:
    """Verify start_date/end_date passed to find_datetimes match record range."""
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 10)
    bar_repo.find_datetimes.return_value = []

    await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    bar_repo.find_datetimes.assert_called_once()
    kwargs = bar_repo.find_datetimes.call_args.kwargs
    assert kwargs["start_date"] == base
    assert kwargs["end_date"] == base + timedelta(minutes=9)
