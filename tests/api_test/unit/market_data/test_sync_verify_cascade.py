"""Unit tests for the hardened sync_verify_cascade job.

Covers:
  - compare_bar_fields: per-field divergence (price 0.01% / volume 5%).
  - _verify_one_symbol: REST↔DB join, no-overlap edge cases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pocketquant.api.market_data.app_services.sync_jobs import (
    PRICE_THRESHOLD_PCT,
    VOLUME_THRESHOLD_PCT,
    _verify_one_symbol,
    compare_bar_fields,
)


def _bar(
    *,
    dt: datetime | None = None,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 10.0,
) -> SimpleNamespace:
    """Lightweight Bar stub — verify code only reads fields, not Bar identity."""
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
            provider=provider,
            bar_repo=bar_repo,
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
            provider=provider,
            bar_repo=bar_repo,
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
            provider=provider,
            bar_repo=bar_repo,
        )
        assert out["compared"] == 3
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
            provider=provider,
            bar_repo=bar_repo,
        )
        assert out["compared"] == 5
        assert out["divergence_count"] == 5
        assert len(out["samples"]) == 3  # truncated for log brevity
        for s in out["samples"]:
            assert s["fields"]["open"] is True
