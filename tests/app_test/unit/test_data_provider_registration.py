# A registered provider missing from DATA_PROVIDER_DEFAULTS would make its unseeded symbols
# fail on their first touch; a default with no registered provider would describe symbols
# that can never be synced.

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.di.adapters import AdaptersProvider
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    DATA_PROVIDER_DEFAULTS,
)
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.exness import exness_client
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from tests.core_test.infra.market_data.conftest import build_settings


class _Stubs(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> Settings:
        return build_settings()

    @provide(scope=Scope.APP)
    def calendars(self) -> TradingCalendarFactory:
        return MagicMock(spec=TradingCalendarFactory)


async def _registered() -> tuple[set[str], set[str]]:
    container = make_async_container(AdaptersProvider(), _Stubs(), skip_validation=True)
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


async def test_without_exness_settings_the_client_is_off_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(500))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        exness_client.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw)
    )
    container = make_async_container(AdaptersProvider(), _Stubs(), skip_validation=True)
    try:
        await container.get(IDataProviderPort)
        await container.get(IRealtimeQuoteProviderPort)
        client = await container.get(ExnessClient)
    finally:
        await container.close()

    assert client.is_configured is False
    assert requests == []
