"""Tests guarding BinanceClient.fetch_ohlcv against in-progress bar capture.

Regression: cron `sync_1m` previously persisted Binance's in-progress kline
(only ~2s of trades) which then locked partial OHLCV in Mongo via
filter_new_bars. fetch_ohlcv must:
  1. Cap params["endTime"] at last_closed_open_ms - 1 (exclusive) so Binance
     never has a chance to return the in-progress kline.
  2. Defense-in-depth: drop any kline whose openTime >= last_closed_open_ms
     even if Binance ignored the cap (clock skew / server off-by-one).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.infrastructure.market_data.binance.binance_client import BinanceClient


def _make_kline(open_time_ms: int, *, close: float = 50_000.0) -> list:
    return [
        open_time_ms,
        str(close),
        str(close + 100),
        str(close - 100),
        str(close),
        "10.5",
        open_time_ms + 59_999,
        "525000.00",
        300,
        "5.0",
        "250000.00",
        "0",
    ]


def _settings() -> MagicMock:
    return MagicMock()


def _capture_get(klines: list[list]) -> tuple[AsyncMock, dict]:
    captured: dict = {}

    async def _side_effect(_path: str, *, params: dict, **_kw):
        captured["params"] = dict(params)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = klines
        mock_resp.headers = {}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    return AsyncMock(side_effect=_side_effect), captured


def _patch_now(now_ms: int):
    """Patch the datetime.now(UTC) call inside binance_client to a fixed ms."""
    fake_now = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
    fake_dt = MagicMock(wraps=datetime)
    fake_dt.now = MagicMock(return_value=fake_now)
    fake_dt.fromtimestamp = datetime.fromtimestamp
    return patch(
        "pocketquant.infrastructure.market_data.binance.binance_client.datetime",
        fake_dt,
    )


class TestEndTimeCap:
    """fetch_ohlcv must cap endTime so the in-progress bar is never requested."""

    @pytest.mark.asyncio
    async def test_endtime_capped_at_last_closed_open_minus_1(self) -> None:
        """now mid-bar → endTime = floor(now/dur)*dur - 1 (exclusive)."""
        bar_dur = 60_000
        bar_open = 1_700_000_400_000  # bar boundary
        # now = 23s into the bar
        now_ms = bar_open + 23_000

        # Server returns the previous closed bar only.
        prev_open = bar_open - bar_dur
        klines = [_make_kline(prev_open)]
        get_mock, captured = _capture_get(klines)

        client = BinanceClient(_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        with _patch_now(now_ms):
            await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=1)

        assert captured["params"]["endTime"] == bar_open - 1

    @pytest.mark.asyncio
    async def test_endtime_at_exact_bar_boundary(self) -> None:
        """now == bar boundary → endTime caps at boundary - 1; previous bar still requested."""
        bar_dur = 60_000
        bar_open = 1_700_000_400_000
        now_ms = bar_open  # exact boundary

        prev_open = bar_open - bar_dur
        klines = [_make_kline(prev_open)]
        get_mock, captured = _capture_get(klines)

        client = BinanceClient(_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        with _patch_now(now_ms):
            bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=1)

        assert captured["params"]["endTime"] == bar_open - 1
        assert len(bars) == 1
        assert bars[0].datetime == datetime.fromtimestamp(prev_open / 1000, tz=UTC)


class TestDefenseInDepthFilter:
    """If Binance returns the in-progress bar anyway, fetch_ohlcv must drop it."""

    @pytest.mark.asyncio
    async def test_drops_in_progress_bar_returned_under_clock_skew(self) -> None:
        """Binance returns kline at last_closed_open_ms — must be filtered out."""
        bar_dur = 60_000
        bar_open = 1_700_000_400_000  # boundary == in-progress bar's openTime
        now_ms = bar_open + 5_000  # 5s into the in-progress bar

        prev_open = bar_open - bar_dur
        # Server (under clock skew) returns BOTH the prev closed bar AND the in-progress one.
        klines = [_make_kline(prev_open), _make_kline(bar_open, close=49_000.0)]
        get_mock, _ = _capture_get(klines)

        client = BinanceClient(_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        with _patch_now(now_ms):
            bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=2)

        assert len(bars) == 1
        assert bars[0].datetime == datetime.fromtimestamp(prev_open / 1000, tz=UTC)


class TestPaginationConsistency:
    """Cap is computed before the loop; multi-chunk fetches stay coherent."""

    @pytest.mark.asyncio
    async def test_pagination_no_duplicates_and_no_in_progress(self) -> None:
        """1500 bars over 2 chunks: ascending, unique openTimes, none == bar_open."""
        bar_dur = 60_000
        bar_open = 1_700_000_400_000
        now_ms = bar_open + 30_000

        # Chunk 1: 1000 bars ending at bar_open - bar_dur (last closed)
        chunk1_last = bar_open - bar_dur
        chunk1 = [_make_kline(chunk1_last - i * bar_dur) for i in range(1000)]
        chunk1.reverse()  # ascending order as Binance returns

        # Chunk 2: previous 500 bars
        chunk2_last = chunk1[0][0] - bar_dur
        chunk2 = [_make_kline(chunk2_last - i * bar_dur) for i in range(500)]
        chunk2.reverse()

        call_count = 0

        async def _side_effect(_path: str, *, params: dict, **_kw):
            nonlocal call_count
            call_count += 1
            body = chunk1 if call_count == 1 else chunk2
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            mock_resp.json.return_value = body
            mock_resp.headers = {}
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        client = BinanceClient(_settings())
        client._http.get = _side_effect  # type: ignore[method-assign]

        cutoff_dt = datetime.fromtimestamp(bar_open / 1000, tz=UTC)
        with _patch_now(now_ms), patch("asyncio.sleep"):
            bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=1500)

        assert call_count == 2
        assert len(bars) == 1500
        # Ascending order
        timestamps = [b.datetime for b in bars]
        assert timestamps == sorted(timestamps)
        # No duplicates
        assert len(set(timestamps)) == 1500
        # No in-progress bar
        assert all(t < cutoff_dt for t in timestamps)
