"""Feed lag: measured in trading minutes, classified, stored, and read back."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.common.constants import CACHE_KEY_DATA_LAG
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status.entities import SyncStatus
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.engine.market_data.app_services import sync_jobs
from pocketquant.engine.market_data.app_services.sync_jobs import _log_feed_transition
from pocketquant.engine.market_data.data_lag_service import (
    STUCK_AFTER_EMPTY_SYNCS,
    STUCK_AFTER_LAG_SECONDS,
    STUCK_AFTER_SYNC_AGE_SECONDS,
    DataLagQueryService,
    FeedState,
    GetDataLagQuery,
    classify_feed,
    compute_data_lag,
    feed_lag_seconds,
)
from pocketquant.engine.market_data.sync_status_service import (
    GetSyncStatusQuery,
    SyncStatusQueryService,
)

CRYPTO = Continuous24x7Calendar()
CME = CmeGlobexCalendarAdapter()
ES = "ES1!:CME_MINI"
# A Monday mid-session, and the Sunday evening Globex open before it.
MONDAY = datetime(2026, 9, 21, 14, 0, 30, tzinfo=UTC)
SUNDAY_OPEN = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
FRIDAY_LAST_BAR = datetime(2026, 9, 18, 20, 59, tzinfo=UTC)


def _bar(symbol: str, dt: datetime, interval: Interval = Interval.MINUTE_1) -> Bar:
    return Bar(
        symbol=symbol,
        interval=interval,
        datetime=dt,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
    )


def _status(symbol: str, interval: Interval, empty_syncs: int = 0) -> SyncStatus:
    return SyncStatus(
        symbol=symbol,
        interval=interval.value,
        status="completed",
        consecutive_empty_fetches=empty_syncs,
    )


class TestFeedLagCountsTradingMinutes:
    def test_a_feed_synced_just_after_the_close_has_no_lag(self) -> None:
        last_closed = MONDAY.replace(second=0) - timedelta(minutes=1)
        assert feed_lag_seconds(last_closed, CRYPTO, MONDAY) == 0

    def test_a_feed_twelve_minutes_late_reports_twelve_minutes(self) -> None:
        latest = MONDAY.replace(second=0) - timedelta(minutes=13)
        assert feed_lag_seconds(latest, CME, MONDAY) == 12 * 60

    def test_a_weekend_is_not_lag(self) -> None:
        """Five minutes after the Sunday open, Friday's last bar is five minutes behind."""
        now = SUNDAY_OPEN + timedelta(minutes=5)
        assert feed_lag_seconds(FRIDAY_LAST_BAR, CME, now) == 5 * 60

    def test_a_closed_market_that_has_caught_up_has_no_lag(self) -> None:
        saturday = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        assert feed_lag_seconds(FRIDAY_LAST_BAR, CME, saturday) == 0

    def test_no_bar_at_all_is_unknown_not_zero(self) -> None:
        assert feed_lag_seconds(None, CME, MONDAY) is None


class TestClassifyFeed:
    def test_within_three_minutes_is_ok(self) -> None:
        assert classify_feed(120, 0, market_open=True) is FeedState.OK

    def test_behind_but_still_inserting_is_delayed(self) -> None:
        assert classify_feed(720, 0, market_open=True) is FeedState.DELAYED

    def test_a_thin_market_skipping_minutes_is_still_only_delayed(self) -> None:
        assert (
            classify_feed(720, STUCK_AFTER_EMPTY_SYNCS - 1, market_open=True) is FeedState.DELAYED
        )

    def test_behind_and_no_longer_inserting_is_stuck(self) -> None:
        assert classify_feed(720, STUCK_AFTER_EMPTY_SYNCS, market_open=True) is FeedState.STUCK

    def test_caught_up_while_shut_is_closed(self) -> None:
        assert classify_feed(0, 50, market_open=False) is FeedState.CLOSED

    def test_no_bars_is_unknown(self) -> None:
        assert classify_feed(None, 0, market_open=True) is FeedState.UNKNOWN

    def test_a_shut_market_is_closed_even_with_the_delayed_tail_missing(self) -> None:
        """The sync stops after the close, so a delayed feed's lag freezes; not a flag."""
        assert classify_feed(840, 0, market_open=False) is FeedState.CLOSED

    def test_far_behind_is_stuck_even_without_an_empty_streak(self) -> None:
        """A sync that stopped running never grows its streak."""
        lag = STUCK_AFTER_LAG_SECONDS + 60
        assert classify_feed(lag, 0, market_open=True) is FeedState.STUCK

    def test_a_sync_that_has_not_run_lately_is_stuck(self) -> None:
        age = STUCK_AFTER_SYNC_AGE_SECONDS + 1
        assert classify_feed(720, 0, market_open=True, sync_age_seconds=age) is FeedState.STUCK

    def test_a_sync_that_ran_this_minute_stays_delayed(self) -> None:
        assert classify_feed(720, 0, market_open=True, sync_age_seconds=40) is FeedState.DELAYED


@pytest.mark.asyncio
async def test_compute_data_lag_reads_the_1m_feed() -> None:
    bar_repo = AsyncMock()
    bar_repo.get_latest = AsyncMock(
        return_value=_bar(ES, MONDAY.replace(second=0) - timedelta(minutes=13))
    )
    sync_status_repo = AsyncMock()
    sync_status_repo.find_one = AsyncMock(return_value=_status(ES, Interval.MINUTE_1))

    snapshot = await compute_data_lag(ES, bar_repo, sync_status_repo, CME, now=MONDAY)

    bar_repo.get_latest.assert_awaited_once_with(ES, Interval.MINUTE_1)
    assert snapshot.state is FeedState.DELAYED
    assert snapshot.lag_seconds == 720
    assert snapshot.is_market_open is True
    assert snapshot.to_cache_dict()["state"] == "delayed"


@pytest.mark.asyncio
async def test_a_1m_sync_that_stopped_running_makes_the_feed_stuck() -> None:
    bar_repo = AsyncMock()
    bar_repo.get_latest = AsyncMock(
        return_value=_bar(ES, MONDAY.replace(second=0) - timedelta(minutes=13))
    )
    status = _status(ES, Interval.MINUTE_1)
    status.last_sync_at = MONDAY - timedelta(minutes=10)
    sync_status_repo = AsyncMock()
    sync_status_repo.find_one = AsyncMock(return_value=status)

    snapshot = await compute_data_lag(ES, bar_repo, sync_status_repo, CME, now=MONDAY)

    assert snapshot.state is FeedState.STUCK


class TestDataLagQueryService:
    @pytest.mark.asyncio
    async def test_no_snapshot_reads_as_unknown(self) -> None:
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)

        result = await DataLagQueryService(cache).get_data_lag(
            GetDataLagQuery(symbol="es1!:cme_mini")
        )

        cache.get.assert_awaited_once_with(CACHE_KEY_DATA_LAG.format(symbol=ES))
        assert result.state is FeedState.UNKNOWN
        assert result.lag_seconds is None

    @pytest.mark.asyncio
    async def test_a_stored_snapshot_round_trips(self) -> None:
        bar_repo = AsyncMock()
        bar_repo.get_latest = AsyncMock(
            return_value=_bar(ES, MONDAY.replace(second=0) - timedelta(minutes=13))
        )
        sync_status_repo = AsyncMock()
        sync_status_repo.find_one = AsyncMock(return_value=None)
        snapshot = await compute_data_lag(ES, bar_repo, sync_status_repo, CME, now=MONDAY)
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=snapshot.to_cache_dict())

        result = await DataLagQueryService(cache).get_data_lag(GetDataLagQuery(symbol=ES))

        assert result.state is FeedState.DELAYED
        assert result.lag_seconds == 720
        assert result.checked_at == snapshot.checked_at


class TestTransitionsAreLoggedOnce:
    @pytest.fixture(autouse=True)
    def _fresh_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # structlog caches a module logger on first use; one first used inside
        # capture_logs() stops being capturable after the next setup_logging(),
        # breaking unrelated tests later in the run. A fresh proxy avoids that.
        monkeypatch.setattr(sync_jobs, "logger", structlog.get_logger("test.data_lag"))

    def _logs(self, previous: dict | None, state: FeedState) -> list[dict]:
        with structlog.testing.capture_logs() as logs:
            _log_feed_transition(previous, state, ES, 720)
        return logs

    def test_an_unchanged_state_is_silent(self) -> None:
        assert self._logs({"state": "delayed"}, FeedState.DELAYED) == []

    def test_becoming_stuck_is_a_warning(self) -> None:
        logs = self._logs({"state": "delayed"}, FeedState.STUCK)
        assert logs[0]["event"] == "data_lag.state_changed"
        assert logs[0]["log_level"] == "warning"

    def test_a_session_opening_delayed_is_info(self) -> None:
        logs = self._logs({"state": "closed"}, FeedState.DELAYED)
        assert logs[0]["log_level"] == "info"
        assert (logs[0]["from_state"], logs[0]["to_state"]) == ("closed", "delayed")

    def test_the_first_reading_counts_as_a_change_from_unknown(self) -> None:
        logs = self._logs(None, FeedState.DELAYED)
        assert logs[0]["from_state"] == "unknown"


class TestSyncStatusCarriesTheFeedLag:
    """Every interval row of a symbol reports that symbol's 1m feed lag."""

    def _service(
        self, statuses: list[SyncStatus], latest_by_interval: dict[Interval, Bar]
    ) -> SyncStatusQueryService:
        sync_status_repo = AsyncMock()
        sync_status_repo.find_all = AsyncMock(return_value=statuses)
        bar_repo = AsyncMock()
        bar_repo.get_latest = AsyncMock(
            side_effect=lambda _sym, interval: latest_by_interval.get(interval)
        )
        bar_repo.count = AsyncMock(return_value=100)
        factory = AsyncMock()
        factory.for_symbol = AsyncMock(return_value=CRYPTO)
        return SyncStatusQueryService(sync_status_repo, bar_repo, factory)

    @pytest.mark.asyncio
    async def test_a_delayed_feed_flags_every_row_and_excuses_the_delay(self) -> None:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        # The feed is 12 minutes behind; the 5m row is as late as the feed makes it.
        latest = {
            Interval.MINUTE_1: _bar(ES, now - timedelta(minutes=13)),
            Interval.MINUTE_5: _bar(ES, now - timedelta(minutes=25), Interval.MINUTE_5),
        }
        service = self._service(
            [_status(ES, Interval.MINUTE_1), _status(ES, Interval.MINUTE_5)], latest
        )

        rows = {r.interval: r for r in await service.get_sync_status(GetSyncStatusQuery())}

        for row in rows.values():
            assert row.is_delayed is True
            assert row.lag_seconds is not None and row.lag_seconds >= 12 * 60
            assert row.is_stuck is False

    @pytest.mark.asyncio
    async def test_a_stalled_feed_marks_the_1m_row_stuck(self) -> None:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        latest = {Interval.MINUTE_1: _bar(ES, now - timedelta(minutes=30))}
        service = self._service(
            [_status(ES, Interval.MINUTE_1, empty_syncs=STUCK_AFTER_EMPTY_SYNCS)], latest
        )

        [row] = await service.get_sync_status(GetSyncStatusQuery())

        assert row.is_delayed is True
        assert row.is_stuck is True

    @pytest.mark.asyncio
    async def test_a_real_time_feed_that_stopped_hours_ago_is_stuck_on_every_row(self) -> None:
        """No streak, no delay excuse: two hours behind is a stopped sync."""
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        btc = "BTCUSDT:BINANCE"
        latest = {
            Interval.MINUTE_1: _bar(btc, now - timedelta(hours=2)),
            Interval.MINUTE_5: _bar(btc, now - timedelta(hours=2), Interval.MINUTE_5),
        }
        service = self._service(
            [_status(btc, Interval.MINUTE_1), _status(btc, Interval.MINUTE_5)], latest
        )

        rows = {r.interval: r for r in await service.get_sync_status(GetSyncStatusQuery())}

        assert rows["1m"].is_stuck is True
        assert rows["5m"].is_stuck is True

    @pytest.mark.asyncio
    async def test_a_stalled_feed_excuses_no_other_row(self) -> None:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        latest = {
            Interval.MINUTE_1: _bar(ES, now - timedelta(minutes=30)),
            Interval.MINUTE_5: _bar(ES, now - timedelta(minutes=30), Interval.MINUTE_5),
        }
        service = self._service(
            [
                _status(ES, Interval.MINUTE_1, empty_syncs=STUCK_AFTER_EMPTY_SYNCS),
                _status(ES, Interval.MINUTE_5),
            ],
            latest,
        )

        rows = {r.interval: r for r in await service.get_sync_status(GetSyncStatusQuery())}

        assert rows["5m"].is_stuck is True
