"""Every provider the routers register has unseeded defaults, and nothing more.

A symbol's suffix names its data provider, so the provider ids registered in
the two routing adapters are the suffixes that can be synced and streamed. A
registered provider missing from ``DATA_PROVIDER_DEFAULTS`` would make its
unseeded symbols fail on their first ``touch``; a default with no registered
provider would describe symbols that can never be synced.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.di.infrastructure import InfrastructureProvider
from pocketquant.app.di.market_data import MarketDataProvider
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    DATA_PROVIDER_DEFAULTS,
)
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from tests.core_test.infra.market_data.conftest import build_settings


class _Stubs(Provider):
    """What the two routers need, without a database behind it."""

    @provide(scope=Scope.APP)
    def settings(self) -> Settings:
        return build_settings()

    @provide(scope=Scope.APP)
    def calendars(self) -> TradingCalendarFactory:
        return MagicMock(spec=TradingCalendarFactory)


async def _registered() -> tuple[set[str], set[str]]:
    container = make_async_container(
        InfrastructureProvider(), MarketDataProvider(), _Stubs(), skip_validation=True
    )
    try:
        rest = await container.get(IDataProviderPort)
        realtime = await container.get(IRealtimeQuoteProviderPort)
        assert isinstance(rest, RoutingDataProviderAdapter)
        assert isinstance(realtime, RoutingRealtimeQuoteAdapter)
        return set(rest._providers), set(realtime._providers)
    finally:
        await container.close()


async def test_both_routers_register_exactly_the_providers_with_defaults() -> None:
    rest, realtime = await _registered()

    assert rest == set(DATA_PROVIDER_DEFAULTS)
    assert realtime == set(DATA_PROVIDER_DEFAULTS)
