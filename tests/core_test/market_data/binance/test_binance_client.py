"""Unit tests for BinanceClient REST data provider.

Uses unittest.mock to patch httpx.AsyncClient — no real network calls, no respx dep.
Covers: interval mapping, kline→Bar fields, pagination cursor, HTTP 429, close().
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.market_data.binance.binance_client import BinanceClient


def _make_kline(
    open_time_ms: int = 1_700_000_000_000,
    open_: float = 50_000.0,
    high: float = 51_000.0,
    low: float = 49_000.0,
    close: float = 50_500.0,
    volume: float = 10.5,
    tick_count: int = 300,
) -> list:
    """Build a minimal Binance kline row (12 positional fields)."""
    close_time_ms = open_time_ms + 59_999
    return [
        open_time_ms,
        str(open_),
        str(high),
        str(low),
        str(close),
        str(volume),
        close_time_ms,
        "525000.00",
        tick_count,
        "5.0",
        "250000.00",
        "0",
    ]


def _make_settings() -> MagicMock:
    return MagicMock()


def _mock_http_response(json_body: list, status_code: int = 200) -> AsyncMock:
    """Return an AsyncMock that mimics httpx.AsyncClient.get returning a given JSON body."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_body
    mock_resp.headers = {}
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=mock_resp,
        )
    else:
        mock_resp.raise_for_status.return_value = None
    get_mock = AsyncMock(return_value=mock_resp)
    return get_mock


class TestKlineToBarMapping:
    """Parametrized mapping tests covering multiple intervals."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "interval,expected_binance_str",
        [
            (Interval.MINUTE_1, "1m"),
            (Interval.MINUTE_5, "5m"),
            (Interval.HOUR_1, "1h"),
            (Interval.DAY_1, "1d"),
        ],
    )
    async def test_interval_maps_to_correct_binance_string(
        self, interval: Interval, expected_binance_str: str
    ) -> None:
        """fetch_ohlcv passes the correct Binance interval string in params."""
        kline = _make_kline()
        get_mock = _mock_http_response([kline])
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        await client.fetch_ohlcv("BTCUSDT:BINANCE", interval, n_bars=1)

        call_kwargs = get_mock.call_args
        fallback = call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        params = call_kwargs.kwargs.get("params", fallback)
        assert params["interval"] == expected_binance_str

    @pytest.mark.asyncio
    async def test_kline_fields_map_correctly(self) -> None:
        """kline_to_bar correctly maps all OHLCV fields and timestamp."""
        ts_ms = 1_700_000_000_000
        kline = _make_kline(
            open_time_ms=ts_ms,
            open_=50_000.0,
            high=51_000.0,
            low=49_000.0,
            close=50_500.0,
            volume=10.5,
            tick_count=300,
        )
        get_mock = _mock_http_response([kline])
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=1)

        assert len(bars) == 1
        bar = bars[0]
        assert bar.symbol == "BTCUSDT:BINANCE"
        assert bar.interval == Interval.MINUTE_1
        assert bar.open == pytest.approx(50_000.0)
        assert bar.high == pytest.approx(51_000.0)
        assert bar.low == pytest.approx(49_000.0)
        assert bar.close == pytest.approx(50_500.0)
        assert bar.volume == pytest.approx(10.5)
        assert bar.tick_count == 300
        expected_dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        assert bar.datetime == expected_dt

    @pytest.mark.asyncio
    async def test_bar_invariants_h_ge_l(self) -> None:
        """All returned bars satisfy high >= low and volume > 0."""
        klines = [_make_kline(open_time_ms=1_700_000_000_000 + i * 60_000) for i in range(5)]
        get_mock = _mock_http_response(klines)
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=5)

        assert all(b.high >= b.low for b in bars)
        assert all(b.volume > 0 for b in bars)


class TestPagination:
    """Tests for single-call and multi-chunk paginated fetches."""

    @pytest.mark.asyncio
    async def test_n_bars_le_1000_makes_single_call(self) -> None:
        """n_bars ≤ 1000 results in exactly one HTTP GET call."""
        klines = [_make_kline(open_time_ms=1_700_000_000_000 + i * 60_000) for i in range(10)]
        get_mock = _mock_http_response(klines)
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=10)

        assert get_mock.await_count == 1
        assert len(bars) == 10

    @pytest.mark.asyncio
    async def test_n_bars_gt_1000_makes_multiple_calls(self) -> None:
        """n_bars > 1000 triggers two HTTP calls; results are merged ascending."""
        chunk1 = [_make_kline(open_time_ms=1_700_060_000_000 + i * 60_000) for i in range(1000)]
        chunk2 = [_make_kline(open_time_ms=1_700_000_000_000 + i * 60_000) for i in range(200)]

        call_count = 0

        async def _side_effect(_path: str, *, params: dict, **_kw):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            body = chunk1 if call_count == 1 else chunk2
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            mock_resp.json.return_value = body
            mock_resp.headers = {}
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        client = BinanceClient(_make_settings())
        client._http.get = _side_effect  # type: ignore[method-assign]

        with patch("asyncio.sleep"):
            bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=1200)

        assert call_count == 2
        assert len(bars) == 1200

    @pytest.mark.asyncio
    async def test_pagination_cursor_starttime_decreases(self) -> None:
        """Second call's startTime is less than first call's startTime."""
        chunk1 = [_make_kline(open_time_ms=1_700_060_000_000 + i * 60_000) for i in range(1000)]
        chunk2 = [_make_kline(open_time_ms=1_700_000_000_000 + i * 60_000) for i in range(500)]

        start_times: list[int] = []
        call_count = 0

        async def _side_effect(_path: str, *, params: dict, **_kw):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            start_times.append(int(params["startTime"]))
            body = chunk1 if call_count == 1 else chunk2
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            mock_resp.json.return_value = body
            mock_resp.headers = {}
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        client = BinanceClient(_make_settings())
        client._http.get = _side_effect  # type: ignore[method-assign]

        with patch("asyncio.sleep"):
            await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=1500)

        assert len(start_times) == 2
        assert start_times[1] < start_times[0], "Window must slide back in time"


class TestErrorHandling:
    """Tests for HTTP error and input validation scenarios."""

    @pytest.mark.asyncio
    async def test_http_429_raises_http_status_error(self) -> None:
        """HTTP 429 must propagate as httpx.HTTPStatusError (not swallowed)."""
        get_mock = _mock_http_response([], status_code=429)
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=10)

    @pytest.mark.asyncio
    async def test_invalid_symbol_raises_value_error(self) -> None:
        """Invalid symbol format raises ValueError before any HTTP call."""
        get_mock = _mock_http_response([])
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        with pytest.raises(ValueError, match="Invalid Binance symbol"):
            await client.fetch_ohlcv("BTC-USDT:BINANCE", Interval.MINUTE_1)

        assert get_mock.await_count == 0

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self) -> None:
        """Empty klines array returns empty bar list without error."""
        get_mock = _mock_http_response([])
        client = BinanceClient(_make_settings())
        client._http.get = get_mock  # type: ignore[method-assign]

        bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, n_bars=100)

        assert bars == []


class TestClose:
    """Tests for httpx client resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose_on_httpx_client(self) -> None:
        """await close() calls aclose on the underlying httpx.AsyncClient."""
        client = BinanceClient(_make_settings())
        mock_aclose = AsyncMock()
        client._http.aclose = mock_aclose  # type: ignore[method-assign]

        await client.close()

        mock_aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_symbols_stub_returns_empty_list(self) -> None:
        """search_symbols stub always returns []."""
        client = BinanceClient(_make_settings())
        result = await client.search_symbols("BTC")
        assert result == []
