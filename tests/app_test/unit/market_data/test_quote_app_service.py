"""Unit tests for QuoteAppService.on_quote_update — volume delta clamping.

Verifies the adapter correctly clamps per-tick delta volume before building
QuoteTick: negative values → 0.0 with warning, None → None passthrough,
positive/zero pass through unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pocketquant.engine.market_data.app_services.quote_app_service import QuoteAppService


def _make_quote_data(volume: float | None, price: float = 50000.0) -> dict:
    """Build minimal quote_data dict as produced by the Binance WS mapper."""
    return {
        "symbol": "BTCUSDT:BINANCE",
        "last_price": price,
        "volume": volume,
        "timestamp": datetime(2026, 5, 8, 10, 0, 0, tzinfo=UTC),
    }


@pytest.fixture
def mock_bar_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.add_tick = AsyncMock()
    return manager


@pytest.fixture
def mock_cache() -> AsyncMock:
    cache = AsyncMock()
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def service(mock_bar_manager: AsyncMock, mock_cache: AsyncMock) -> QuoteAppService:
    """QuoteAppService with all external dependencies mocked."""
    settings = MagicMock()
    provider = MagicMock()
    return QuoteAppService(
        settings=settings,
        cache=mock_cache,
        bar_manager=mock_bar_manager,
        provider=provider,
    )


class TestOnQuoteUpdateVolumeClamping:
    """on_quote_update passes clamped delta volume to QuoteTick."""

    @pytest.mark.asyncio
    async def test_positive_delta_passes_through(
        self, service: QuoteAppService, mock_bar_manager: AsyncMock
    ) -> None:
        """Positive delta volume is forwarded unchanged to QuoteTick."""
        await service.on_quote_update(_make_quote_data(volume=0.05))

        mock_bar_manager.add_tick.assert_called_once()
        tick = mock_bar_manager.add_tick.call_args[0][0]
        assert tick.volume == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_negative_delta_clamped_to_zero_and_warns(
        self, service: QuoteAppService, mock_bar_manager: AsyncMock
    ) -> None:
        """Negative delta is clamped to 0.0; a warning is logged."""
        with patch(
            "pocketquant.engine.market_data.app_services.quote_app_service.logger"
        ) as mock_logger:
            await service.on_quote_update(_make_quote_data(volume=-0.01))

        mock_bar_manager.add_tick.assert_called_once()
        tick = mock_bar_manager.add_tick.call_args[0][0]
        assert tick.volume == pytest.approx(0.0)
        mock_logger.warning.assert_called_once()
        # Confirm event name and raw value surfaced in log
        call_kwargs = mock_logger.warning.call_args
        assert "negative_volume" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_none_volume_passes_through_as_none(
        self, service: QuoteAppService, mock_bar_manager: AsyncMock
    ) -> None:
        """None volume means no volume data; QuoteTick.volume must be None."""
        await service.on_quote_update(_make_quote_data(volume=None))

        mock_bar_manager.add_tick.assert_called_once()
        tick = mock_bar_manager.add_tick.call_args[0][0]
        assert tick.volume is None

    @pytest.mark.asyncio
    async def test_zero_volume_is_processed(
        self, service: QuoteAppService, mock_bar_manager: AsyncMock
    ) -> None:
        """Zero volume tick is a valid delta (no trade qty); tick still forwarded."""
        await service.on_quote_update(_make_quote_data(volume=0))

        mock_bar_manager.add_tick.assert_called_once()
        tick = mock_bar_manager.add_tick.call_args[0][0]
        assert tick.volume == pytest.approx(0.0)
        # Price must still be set (OHLC update)
        assert tick.price == pytest.approx(50000.0)
