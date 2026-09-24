"""Fallback order, and the assumptions the routing adapter makes out loud.

The crypto path cannot exercise any of this: production registers one provider,
so every fallback branch is dead code until a second one exists. These fakes are
the only place the routing is observable before Phase 5.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import AssetClass, Interval
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from tests.core_test.infra.market_data.conftest import build_settings, lookup_returning

FUTURES = "ES1!:CME_MINI"
MAP = {
    AssetClass.CRYPTO_SPOT: ["binance"],
    AssetClass.INDEX_FUTURE: ["tradingview", "binance"],
}


def _bar() -> Bar:
    return Bar(
        symbol=FUTURES,
        interval=Interval.MINUTE_1,
        datetime=None,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
    )


def _provider(result: list[Bar] | Exception) -> AsyncMock:
    provider = AsyncMock()
    if isinstance(result, Exception):
        provider.fetch_ohlcv = AsyncMock(side_effect=result)
    else:
        provider.fetch_ohlcv = AsyncMock(return_value=result)
    return provider


def _adapter(
    providers: dict[str, AsyncMock],
    *,
    asset_class: AssetClass | None = AssetClass.INDEX_FUTURE,
    overrides: dict[str, list[str]] | None = None,
) -> RoutingDataProviderAdapter:
    return RoutingDataProviderAdapter(
        providers=providers,  # pyright: ignore[reportArgumentType]
        settings=build_settings(MAP, overrides),
        symbol_lookup=lookup_returning(asset_class),  # pyright: ignore[reportArgumentType]
    )


async def _fetch(adapter: RoutingDataProviderAdapter) -> list[Bar]:
    return await adapter.fetch_ohlcv(symbol=FUTURES, interval=Interval.MINUTE_1, n_bars=10)


@pytest.mark.asyncio
async def test_primary_result_returned() -> None:
    primary, secondary = _provider([_bar()]), _provider([_bar(), _bar()])

    bars = await _fetch(_adapter({"tradingview": primary, "binance": secondary}))

    assert len(bars) == 1
    secondary.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_exception_falls_through_to_secondary() -> None:
    primary, secondary = _provider(RuntimeError("scraper down")), _provider([_bar()])

    bars = await _fetch(_adapter({"tradingview": primary, "binance": secondary}))

    assert len(bars) == 1
    secondary.fetch_ohlcv.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_result_falls_through_to_secondary() -> None:
    primary, secondary = _provider([]), _provider([_bar()])

    bars = await _fetch(_adapter({"tradingview": primary, "binance": secondary}))

    assert len(bars) == 1
    secondary.fetch_ohlcv.assert_awaited_once()


@pytest.mark.asyncio
async def test_every_provider_answering_empty_returns_an_empty_list() -> None:
    """Nobody raised, so nobody is broken — this is a quiet market."""
    primary, secondary = _provider([]), _provider([])

    bars = await _fetch(_adapter({"tradingview": primary, "binance": secondary}))

    assert bars == []


@pytest.mark.asyncio
async def test_an_outage_is_raised_rather_than_reported_as_an_empty_market() -> None:
    """Swallowing the failure turns a dead venue into a successful sync.

    Before routing existed a provider exception reached ``sync_one``, which
    logged ``market_data.sync.failed`` and set the symbol's status to
    ``error``. Returning ``[]`` instead would report ``completed`` with no
    progress, and would leave ``fetch_with_retry`` retrying the failure as
    though it were emptiness — three calls at a venue that is rate-limiting us.
    """
    primary, secondary = _provider([]), _provider(RuntimeError("also down"))

    with pytest.raises(RuntimeError, match="also down"):
        await _fetch(_adapter({"tradingview": primary, "binance": secondary}))


@pytest.mark.asyncio
async def test_a_provider_that_answers_hides_an_earlier_failure() -> None:
    """Fallback still works: one bad provider is not an outage."""
    primary, secondary = _provider(RuntimeError("scraper down")), _provider([_bar()])

    bars = await _fetch(_adapter({"tradingview": primary, "binance": secondary}))

    assert len(bars) == 1


@pytest.mark.asyncio
async def test_unknown_provider_id_is_skipped() -> None:
    """A provider named in config but never registered must not end the walk."""
    secondary = _provider([_bar()])

    bars = await _fetch(_adapter({"binance": secondary}))

    assert len(bars) == 1
    secondary.fetch_ohlcv.assert_awaited_once()


@pytest.mark.asyncio
async def test_symbol_override_selects_the_overridden_provider_first() -> None:
    """G4 evidence: moving one symbol to another venue is a config edit.

    Nothing in ``engine/`` or ``app/`` participates — the override is read by
    the routing adapter through Settings, and every consumer above it still
    holds the same ``IDataProviderPort`` it held before.
    """
    primary, secondary = _provider([_bar()]), _provider([_bar(), _bar()])

    bars = await _fetch(
        _adapter(
            {"tradingview": primary, "binance": secondary},
            overrides={FUTURES: ["binance"]},
        )
    )

    assert len(bars) == 2
    primary.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_third_provider_serves_only_the_symbol_overridden_to_it() -> None:
    """G4 evidence: a new venue is reached only through configuration.

    The third provider is registered beside the existing two and named by one
    override. A symbol of the same asset class without the override never
    reaches it.
    """
    tradingview, binance, third = _provider([_bar()]), _provider([_bar()]), _provider([_bar()])
    adapter = _adapter(
        {"tradingview": tradingview, "binance": binance, "third": third},
        overrides={FUTURES: ["third"]},
    )

    await _fetch(adapter)
    await adapter.fetch_ohlcv(symbol="NQ1!:CME_MINI", interval=Interval.MINUTE_1)

    assert [c.kwargs["symbol"] for c in third.fetch_ohlcv.await_args_list] == [FUTURES]
    assert [c.kwargs["symbol"] for c in tradingview.fetch_ohlcv.await_args_list] == [
        "NQ1!:CME_MINI"
    ]
    binance.fetch_ohlcv.assert_not_awaited()


class TestTheAdapterSaysWhatItAssumed:
    """Two silent assumptions are made audible, once per symbol."""

    @pytest.mark.asyncio
    async def test_an_unseeded_symbol_warns_that_it_assumed_crypto(self) -> None:
        """Seeding must precede the first sync, so say so when it did not.

        An unseeded futures symbol routes to a crypto venue that has no such
        instrument, returns nothing, and so never reaches the ``touch`` that
        would have created its document — the miss is self-reinforcing and the
        symbol lookup caches it for 60s in between.
        """
        adapter = _adapter({"binance": _provider([_bar()])}, asset_class=None)

        with structlog.testing.capture_logs() as logs:
            await _fetch(adapter)

        unseeded = [e for e in logs if e["event"] == "market_data.routing.unseeded_symbol"]
        assert len(unseeded) == 1
        assert unseeded[0]["log_level"] == "warning"
        assert unseeded[0]["assumed_asset_class"] == AssetClass.CRYPTO_SPOT.value

    @pytest.mark.asyncio
    async def test_the_unseeded_warning_is_not_repeated_per_fetch(self) -> None:
        """It sits on a per-minute path; once per symbol is the whole point."""
        adapter = _adapter({"binance": _provider([_bar()])}, asset_class=None)

        with structlog.testing.capture_logs() as logs:
            await _fetch(adapter)
            await _fetch(adapter)
            await _fetch(adapter)

        assert len([e for e in logs if e["event"] == "market_data.routing.unseeded_symbol"]) == 1

    @pytest.mark.asyncio
    async def test_resolving_no_provider_at_all_warns(self) -> None:
        """Reachable by configuration, not just by an unmapped asset class.

        Setting MARKET_DATA_PROVIDERS replaces the whole mapping rather than
        merging into it, so an override naming one asset class leaves every
        other class with nothing. Returning no bars in silence is
        indistinguishable from a dead venue.
        """
        adapter = RoutingDataProviderAdapter(
            providers={"binance": _provider([_bar()])},  # pyright: ignore[reportArgumentType]
            settings=build_settings({AssetClass.INDEX_FUTURE: ["tradingview"]}),
            symbol_lookup=lookup_returning(AssetClass.CRYPTO_SPOT),  # pyright: ignore[reportArgumentType]
        )

        with structlog.testing.capture_logs() as logs:
            bars = await _fetch(adapter)

        assert bars == []
        no_provider = [e for e in logs if e["event"] == "market_data.routing.no_provider"]
        assert len(no_provider) == 1
        assert no_provider[0]["log_level"] == "warning"
