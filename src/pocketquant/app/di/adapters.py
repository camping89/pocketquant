"""Adapters provider: the venue adapters behind the ports.

Each routing adapter maps a provider id to its venue adapter. The key is the
provider id a symbol's suffix names (BTCUSDT:BINANCE -> "binance",
XAUUSD:EXNESS -> "exness"). Adding a provider is one entry in each router here
and one in DATA_PROVIDER_DEFAULTS; the routing adapters implement the same
ports, so every consumer above them is unchanged. ``BrokerFactory`` builds the broker adapters.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.core.common.messaging import EventBus
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
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.exness.exness_adapter import ExnessAdapter
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.exness.exness_quote_adapter import ExnessQuoteAdapter
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.safeguards_repository import (
    SafeguardsRepository,
)


class AdaptersProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_safeguards(self, settings: Settings, repo: SafeguardsRepository) -> Safeguards:
        """The env caps plus the stored entry pause, loaded before any strategy starts."""
        return Safeguards(
            live_trading=settings.exness_live_trading,
            daily_loss_cap=settings.exness_daily_loss_cap,
            max_lots=settings.exness_max_lots,
            leverage=settings.exness_leverage,
            risk_per_trade=settings.exness_risk_per_trade,
            entries_paused=await repo.load_entries_paused(),
        )

    @provide(scope=Scope.APP)
    def get_broker_factory(
        self,
        event_bus: EventBus,
        safeguards: Safeguards,
        exness_client: ExnessClient,
        position_repository: PositionRepository,
    ) -> BrokerFactory:
        return BrokerFactory(
            event_bus,
            exness_client=exness_client,
            position_repository=position_repository,
            safeguards=safeguards,
        )

    @provide(scope=Scope.APP)
    async def get_exness_client(self, settings: Settings) -> AsyncIterator[ExnessClient]:
        """One signed client for history and quotes; it sends nothing until used."""
        client = ExnessClient(settings)
        yield client
        await client.close()

    @provide(scope=Scope.APP)
    def get_data_provider(
        self, settings: Settings, exness_client: ExnessClient
    ) -> IDataProviderPort:
        return RoutingDataProviderAdapter(
            providers={
                "binance": BinanceAdapter(settings=settings),
                "exness": ExnessAdapter(exness_client),
            },
        )

    @provide(scope=Scope.APP)
    def get_realtime_quote_provider(
        self, exness_client: ExnessClient
    ) -> IRealtimeQuoteProviderPort:
        return RoutingRealtimeQuoteAdapter(
            providers={
                "binance": BinanceWebSocketAdapter(),
                "exness": ExnessQuoteAdapter(exness_client),
            },
        )
