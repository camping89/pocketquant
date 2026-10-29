from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS
from pocketquant.engine.market_data.sync_internals.bar_filters import (
    drop_misaligned_bars,
    filter_new_bars,
)

SYMBOL = "BTCUSDT:BINANCE"
CALENDAR = Continuous24x7Calendar()
EURUSD = EXNESS_CALENDARS[0]


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


# naive=True mimics tz-naive Mongo storage.
def _existing_docs(times: list[datetime], naive: bool = True) -> list[dict]:
    return [
        {"_id": f"id-{i}", "datetime": (t.replace(tzinfo=None) if naive else t)}
        for i, t in enumerate(times)
    ]


@pytest.fixture
def bar_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_datetimes = AsyncMock(return_value=[])
    return repo


# 99 contiguous bars stored; a 100-bar fetch over the same range plus one new tail keeps
# only the tail.
@pytest.mark.asyncio
async def test_continuous_db_keeps_only_new(bar_repo: AsyncMock) -> None:
    base = datetime(2026, 5, 7, 2, 0, tzinfo=UTC)
    records = _series(base, 100)
    bar_repo.find_datetimes.return_value = _existing_docs(
        [base + timedelta(minutes=i) for i in range(99)]
    )

    result = await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    assert len(result) == 1
    assert result[0].datetime == base + timedelta(minutes=99)


# 3 bars stored at the end; a 5000-bar fetch over 3.5 days keeps the other 4997.
@pytest.mark.asyncio
async def test_tail_gap_keeps_all_below_latest(bar_repo: AsyncMock) -> None:
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


# Stored 02:00..02:30 and 03:00..03:38; a 100-bar fetch 02:00..03:39 keeps the 29-bar hole
# plus the 03:39 tail.
@pytest.mark.asyncio
async def test_middle_hole_keeps_hole_bars(bar_repo: AsyncMock) -> None:
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


# Mongo returns tz-naive datetimes while records are tz-aware.
@pytest.mark.asyncio
async def test_naive_mongo_datetime_matches_aware_record(bar_repo: AsyncMock) -> None:
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
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 5)
    bar_repo.find_datetimes.return_value = []

    with structlog.testing.capture_logs() as logs:
        await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    matching = [e for e in logs if e.get("event") == "market_data.sync.filtered_existing"]
    assert matching == []


@pytest.mark.asyncio
async def test_query_uses_min_max_of_record_datetimes(bar_repo: AsyncMock) -> None:
    base = datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    records = _series(base, 10)
    bar_repo.find_datetimes.return_value = []

    await filter_new_bars(records, SYMBOL, Interval.MINUTE_1, bar_repo)

    bar_repo.find_datetimes.assert_called_once()
    kwargs = bar_repo.find_datetimes.call_args.kwargs
    assert kwargs["start_date"] == base
    assert kwargs["end_date"] == base + timedelta(minutes=9)


class TestDropMisalignedBarsFollowsTheCalendar:
    # An Exness week opens on Sunday 00:00 UTC, so a weekly bar stamped on
    # Monday 00:00 UTC is misaligned there and aligned on 24/7, and the reverse.
    MONDAY_MIDNIGHT = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    EXNESS_WEEK_OPEN = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)

    def _weekly(self, ts: datetime) -> Bar:
        bar = _bar(ts)
        bar.interval = Interval.WEEK_1
        return bar

    def test_same_bars_drop_the_opposite_way_on_each_calendar(self) -> None:
        bars = [self._weekly(self.MONDAY_MIDNIGHT), self._weekly(self.EXNESS_WEEK_OPEN)]

        kept_247 = drop_misaligned_bars(bars, Interval.WEEK_1, CALENDAR)
        kept_exness = drop_misaligned_bars(bars, Interval.WEEK_1, EURUSD)

        assert [b.datetime for b in kept_247] == [self.MONDAY_MIDNIGHT]
        assert [b.datetime for b in kept_exness] == [self.EXNESS_WEEK_OPEN]

    def test_warning_names_the_calendar_that_rejected_the_bars(self) -> None:
        with structlog.testing.capture_logs() as logs:
            drop_misaligned_bars([self._weekly(self.MONDAY_MIDNIGHT)], Interval.WEEK_1, EURUSD)

        dropped = [e for e in logs if e.get("event") == "market_data.sync.misaligned_bars_dropped"]
        assert len(dropped) == 1
        assert dropped[0]["calendar_id"] == EURUSD.calendar_id
        assert dropped[0]["count"] == 1
