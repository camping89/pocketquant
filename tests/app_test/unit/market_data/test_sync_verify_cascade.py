from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.app_services import sync_jobs
from pocketquant.engine.market_data.app_services.sync_jobs import (
    PRICE_THRESHOLD_PCT,
    VOLUME_THRESHOLD_PCT,
    _verify_one_symbol,
    compare_bar_fields,
)


# The verify code only reads fields, not Bar identity.
def _bar(
    *,
    dt: datetime | None = None,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 10.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        datetime=dt or datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class TestCompareBarFields:
    def test_identical_bars_no_divergence(self) -> None:
        a = _bar()
        b = _bar()
        result = compare_bar_fields(a, b)
        assert result == {
            "open": False,
            "high": False,
            "low": False,
            "close": False,
            "volume": False,
        }

    def test_open_divergent_above_threshold(self) -> None:
        a = _bar(open_=80_000.0)
        # 0.02% drift on $80k → $16, well above 0.01% threshold.
        b = _bar(open_=80_016.0)
        result = compare_bar_fields(a, b)
        assert result["open"] is True
        assert result["high"] is False

    def test_close_within_tolerance(self) -> None:
        a = _bar(close=80_000.0)
        # Drift of $4 on $80k = 0.005%, below 0.01% threshold.
        b = _bar(close=80_004.0)
        result = compare_bar_fields(a, b)
        assert result["close"] is False

    def test_volume_divergent_above_5pct(self) -> None:
        a = _bar(volume=10.0)
        b = _bar(volume=10.6)  # +6% drift
        result = compare_bar_fields(a, b)
        assert result["volume"] is True

    def test_volume_within_5pct(self) -> None:
        a = _bar(volume=10.0)
        b = _bar(volume=10.4)  # +4% drift, below threshold
        result = compare_bar_fields(a, b)
        assert result["volume"] is False

    def test_thresholds_are_calibrated(self) -> None:
        # Guard against accidental loosening: price 0.01% catches BTC $8 drift;
        # volume 5% allows exchange rounding noise.
        assert PRICE_THRESHOLD_PCT == 0.0001
        assert VOLUME_THRESHOLD_PCT == 0.05


def _ts(minute: int) -> datetime:
    return datetime(2026, 5, 8, 10, minute, tzinfo=UTC)


class TestVerifyOneSymbol:
    @pytest.mark.asyncio
    async def test_rest_empty_short_circuits(self) -> None:
        provider = SimpleNamespace(fetch_ohlcv=AsyncMock(return_value=[]))
        bar_repo = SimpleNamespace(find=AsyncMock())

        out = await _verify_one_symbol(
            "BINANCE:BTCUSDT",
            provider=provider,  # pyright: ignore[reportArgumentType]
            bar_repo=bar_repo,  # pyright: ignore[reportArgumentType]
        )
        assert out["rest_empty"] is True
        assert out["compared"] == 0
        bar_repo.find.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cascade_empty_returns_flag(self) -> None:
        rest = [_bar(dt=_ts(0))]
        provider = SimpleNamespace(fetch_ohlcv=AsyncMock(return_value=rest))
        bar_repo = SimpleNamespace(find=AsyncMock(return_value=[]))

        out = await _verify_one_symbol(
            "BINANCE:BTCUSDT",
            provider=provider,  # pyright: ignore[reportArgumentType]
            bar_repo=bar_repo,  # pyright: ignore[reportArgumentType]
        )
        assert out["cascade_empty"] is True
        assert out["compared"] == 0

    @pytest.mark.asyncio
    async def test_no_divergence_when_data_matches(self) -> None:
        rest = [_bar(dt=_ts(m)) for m in (0, 5, 10)]
        cascade = [_bar(dt=_ts(m)) for m in (0, 5, 10)]
        provider = SimpleNamespace(fetch_ohlcv=AsyncMock(return_value=rest))
        bar_repo = SimpleNamespace(find=AsyncMock(return_value=cascade))

        out = await _verify_one_symbol(
            "BINANCE:BTCUSDT",
            provider=provider,  # pyright: ignore[reportArgumentType]
            bar_repo=bar_repo,  # pyright: ignore[reportArgumentType]
        )
        assert out["compared"] == 2  # the newest bucket is left out
        assert out["divergence_count"] == 0
        assert out["samples"] == []

    @pytest.mark.asyncio
    async def test_divergence_captured_and_sample_truncated_to_3(self) -> None:
        rest = [_bar(dt=_ts(m), open_=80_000.0) for m in (0, 5, 10, 15, 20)]
        # All cascade bars drift open by 0.05% → all five divergent.
        cascade = [_bar(dt=_ts(m), open_=80_040.0) for m in (0, 5, 10, 15, 20)]
        provider = SimpleNamespace(fetch_ohlcv=AsyncMock(return_value=rest))
        bar_repo = SimpleNamespace(find=AsyncMock(return_value=cascade))

        out = await _verify_one_symbol(
            "BINANCE:BTCUSDT",
            provider=provider,  # pyright: ignore[reportArgumentType]
            bar_repo=bar_repo,  # pyright: ignore[reportArgumentType]
        )
        assert out["compared"] == 4  # the newest bucket is left out
        assert out["divergence_count"] == 4
        assert len(out["samples"]) == 3  # truncated for log brevity
        for s in out["samples"]:
            assert s["fields"]["open"] is True

    @pytest.mark.asyncio
    async def test_newest_bucket_short_of_its_last_minute_is_not_compared(self) -> None:
        # The verify runs seconds before sync_1m stores the newest 1m bar, so the
        # newest stored bucket lacks a minute of volume. An older bucket that
        # diverges must still count. Bars arrive newest first, as some providers return.
        rest = [_bar(dt=_ts(m)) for m in (15, 10, 5, 0)]
        cascade = [_bar(dt=_ts(0)), _bar(dt=_ts(5), open_=100.5), _bar(dt=_ts(10))]
        cascade.append(_bar(dt=_ts(15), volume=8.0))
        provider = SimpleNamespace(fetch_ohlcv=AsyncMock(return_value=rest))
        bar_repo = SimpleNamespace(find=AsyncMock(return_value=cascade))

        out = await _verify_one_symbol(
            "BINANCE:BTCUSDT",
            provider=provider,  # pyright: ignore[reportArgumentType]
            bar_repo=bar_repo,  # pyright: ignore[reportArgumentType]
        )
        assert out["compared"] == 3
        assert out["divergence_count"] == 1
        assert out["samples"][0]["datetime"] == _ts(5).isoformat()


_SYMBOL = "BTCUSDT:BINANCE"


class _BarRepo:
    def __init__(self, bars: list[Bar]) -> None:
        self.bars = bars

    async def find(self, symbol, interval, start_date=None, end_date=None, limit=5000):  # noqa: ANN001
        matching = [
            b
            for b in self.bars
            if b.symbol == symbol
            and b.interval == interval
            and start_date <= b.datetime <= end_date  # type: ignore[operator]
        ]
        return sorted(matching, key=lambda b: b.datetime, reverse=True)[:limit]  # type: ignore[arg-type, return-value]


class _Container:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    async def get(self, cls):  # noqa: ANN001
        return self._mapping[cls]


def _bar_at(interval: Interval, dt: datetime, close: float = 100.5) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        interval=interval,
        datetime=dt,
        open=100.0,
        high=101.0,
        low=99.0,
        close=close,
        volume=10.0,
    )


# Three 1m bars per day; the matching stored 1d aggregates them.
def _minutes(day: datetime) -> list[Bar]:
    return [
        _bar_at(Interval.MINUTE_1, day),
        _bar_at(Interval.MINUTE_1, day + timedelta(hours=12)),
        _bar_at(Interval.MINUTE_1, day + timedelta(hours=23, minutes=59)),
    ]


def _daily(day: datetime, close: float = 100.5) -> Bar:
    bar = _bar_at(Interval.DAY_1, day, close)
    bar.volume = 30.0
    return bar


def _today() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def _run_verify(monkeypatch: pytest.MonkeyPatch, bars: list[Bar]) -> list[dict]:
    tracked_repo = MagicMock()
    tracked_repo.list_all = AsyncMock(return_value=[SimpleNamespace(symbol=_SYMBOL)])
    history = MagicMock()
    history.record_start = AsyncMock(return_value="hist-1")
    history.record_finish = AsyncMock()
    factory = MagicMock()
    factory.for_symbol = AsyncMock(return_value=Continuous24x7Calendar())
    container = _Container(
        {
            TrackedSymbolRepository: tracked_repo,
            BarRepository: _BarRepo(bars),
            IDataProviderPort: SimpleNamespace(fetch_ohlcv=AsyncMock(return_value=[])),
            TradingCalendarFactory: factory,
            JobHistoryRepository: history,
        }
    )
    monkeypatch.setattr(sync_jobs, "_container", container)
    # A cached module logger ignores capture_logs once it has emitted.
    monkeypatch.setattr(sync_jobs, "logger", structlog.get_logger(sync_jobs.__name__))
    with structlog.testing.capture_logs() as logs:
        await sync_jobs.sync_verify_cascade()
    return [e for e in logs if e["event"] == "cascade.daily_divergence"]


class TestDailyBarCheck:
    @pytest.mark.asyncio
    async def test_a_stored_day_that_differs_from_its_minutes_warns_with_the_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        days = [_today() - timedelta(days=n) for n in (3, 2, 1)]
        bars = [b for day in days for b in _minutes(day)]
        bars += [_daily(days[0]), _daily(days[1], close=120.0), _daily(days[2])]

        warnings = await _run_verify(monkeypatch, bars)

        assert len(warnings) == 1
        assert warnings[0]["log_level"] == "warning"
        assert warnings[0]["symbol"] == _SYMBOL
        assert warnings[0]["datetime"] == days[1].isoformat()
        assert warnings[0]["fields"] == ["close"]

    @pytest.mark.asyncio
    async def test_equal_days_log_no_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        days = [_today() - timedelta(days=n) for n in (3, 2, 1)]
        bars = [b for day in days for b in _minutes(day)] + [_daily(day) for day in days]

        assert await _run_verify(monkeypatch, bars) == []

    @pytest.mark.asyncio
    async def test_the_day_in_progress_is_never_compared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        today = _today()
        bars = [_bar_at(Interval.MINUTE_1, today), _daily(today, close=120.0)]

        assert await _run_verify(monkeypatch, bars) == []

    @pytest.mark.asyncio
    async def test_a_day_missing_on_either_side_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        no_daily, no_minutes = _today() - timedelta(days=2), _today() - timedelta(days=1)
        bars = [*_minutes(no_daily), _daily(no_minutes, close=120.0)]

        assert await _run_verify(monkeypatch, bars) == []
