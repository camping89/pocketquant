"""An unseeded symbol's calendar comes from the data provider its suffix names.

Defaulting every unseeded symbol to 24/7 would let a session-hours instrument
synced before seeding be read as always open: closed-market skips would never
fire and every weekend would count as missing bars.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
)
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CME_GLOBEX_EQUITY,
    CALENDAR_CRYPTO_24_7,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory


def _factory(record: Symbol | None) -> TradingCalendarFactory:
    lookup = MagicMock()
    lookup.get = AsyncMock(return_value=record)
    return TradingCalendarFactory(symbol_lookup=lookup)


@pytest.mark.asyncio
async def test_an_unseeded_binance_symbol_is_24x7() -> None:
    calendar = await _factory(None).for_symbol("DOGEUSDT:BINANCE")

    assert calendar.calendar_id == CALENDAR_CRYPTO_24_7


@pytest.mark.asyncio
async def test_an_unseeded_tradingview_symbol_gets_the_cme_calendar() -> None:
    calendar = await _factory(None).for_symbol("ES1!:TRADINGVIEW")

    assert calendar.calendar_id == CALENDAR_CME_GLOBEX_EQUITY


@pytest.mark.asyncio
async def test_an_unseeded_symbol_of_an_unregistered_provider_is_refused() -> None:
    """Better an error than a gold symbol silently trading 24/7."""
    with pytest.raises(UnknownDataProviderError, match="'mt5'"):
        await _factory(None).for_symbol("XAUUSD:MT5")


@pytest.mark.asyncio
async def test_a_seeded_record_wins_over_the_provider_default() -> None:
    seeded = Symbol.create("ES1!:TRADINGVIEW", asset_class=AssetClass.CRYPTO_SPOT)

    calendar = await _factory(seeded).for_symbol("ES1!:TRADINGVIEW")

    assert calendar.calendar_id == CALENDAR_CRYPTO_24_7
