"""Adapters provider: the venue adapters behind the ports.

Each routing adapter maps a provider id to its venue adapter. The key is the
provider id a symbol's suffix names (BTCUSDT:BINANCE -> "binance",
ES1!:TRADINGVIEW -> "tradingview", XAUUSD:EXNESS -> "exness"). Adding a
provider is one entry in each router here and one in DATA_PROVIDER_DEFAULTS;
the routing adapters implement the same ports, so every consumer above them is
unchanged. ``BrokerFactory`` builds the broker adapters.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.binance.binance_adapter import BinanceAdapter
from pocketquant.core.infra.binance.binance_websocket_adapter import (
    BinanceWebSocketAdapter,
)
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.exness.exness_adapter import ExnessAdapter
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.exness.exness_quote_adapter import ExnessQuoteAdapter
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from pocketquant.core.infra.tradingview.tradingview_adapter import TradingViewAdapter
from pocketquant.core.infra.tradingview.tradingview_quote_adapter import TradingViewQuoteAdapter
from pocketquant.core.infra.tradingview.tvdatafeed_client import TvDatafeedClient


class AdaptersProvider(Provider):
    broker_factory = provide(BrokerFactory, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_tradingview_client(self, settings: Settings) -> TvDatafeedClient:
        # One scraper session for history and quotes: its lock then serialises
        # both, instead of two sessions bursting at an unofficial endpoint.
        return TvDatafeedClient(settings=settings)

    @provide(scope=Scope.APP)
    async def get_exness_client(self, settings: Settings) -> AsyncIterator[ExnessClient]:
        """One signed client for history and quotes; it sends nothing until used."""
        client = ExnessClient(settings)
        yield client
        await client.close()

    @provide(scope=Scope.APP)
    def get_data_provider(
        self,
        settings: Settings,
        calendar_factory: TradingCalendarFactory,
        tradingview_client: TvDatafeedClient,
        exness_client: ExnessClient,
    ) -> IDataProviderPort:
        return RoutingDataProviderAdapter(
            providers={
                "binance": BinanceAdapter(settings=settings),
                "tradingview": TradingViewAdapter(
                    client=tradingview_client,
                    settings=settings,
                    calendar_factory=calendar_factory,
                ),
                "exness": ExnessAdapter(exness_client),
            },
        )

    @provide(scope=Scope.APP)
    def get_realtime_quote_provider(
        self,
        settings: Settings,
        calendar_factory: TradingCalendarFactory,
        tradingview_client: TvDatafeedClient,
        exness_client: ExnessClient,
    ) -> IRealtimeQuoteProviderPort:
        return RoutingRealtimeQuoteAdapter(
            providers={
                "binance": BinanceWebSocketAdapter(),
                "tradingview": TradingViewQuoteAdapter(
                    client=tradingview_client,
                    settings=settings,
                    calendar_factory=calendar_factory,
                ),
                "exness": ExnessQuoteAdapter(exness_client),
            },
        )
