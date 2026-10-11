"""Adapters provider: venue adapters behind the ports.

``SyncPolicies`` builds the per-exchange data and quote adapters;
``BrokerFactory`` builds the broker adapters.
"""

from dishka import Provider, Scope, provide

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.domain.brokers.interfaces import IBroker
from pocketquant.core.infra.binance.binance_client import BinanceClient
from pocketquant.core.infra.binance.binance_websocket_client import BinanceWebSocketClient
from pocketquant.core.infra.brokers.okx.okx_broker import OKXBroker
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.engine.market_data.sync_policy import SyncPolicies, binance_policy


class BrokerFactory:
    """Factory for creating broker instances from configuration.

    Holds the application ``EventBus`` so paper brokers can subscribe to
    ``BarCompletedEvent`` and auto-fill SL/TP during live paper trading.
    Real brokers (OKX) ignore the bus — they receive fills from the venue.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def create(self, broker_type: str, config: dict) -> IBroker:
        """Create broker instance from type and config.

        Args:
            broker_type: "paper" or "okx"
            config: Broker-specific configuration

        Returns:
            IBroker instance

        Raises:
            ValueError: If broker type is unknown
        """
        if broker_type == "paper":
            return PaperBroker(
                initial_balance=config.get("initial_balance", 100_000.0),
                slippage_percent=config.get("slippage_percent", 0.001),
                fill_delay_ms=config.get("fill_delay_ms", 50),
                currency=config.get("currency", "USDT"),
                event_bus=self._event_bus,
            )

        elif broker_type == "okx":
            # Validate required OKX credentials
            api_key = config.get("api_key")
            api_secret = config.get("api_secret")
            passphrase = config.get("passphrase")

            if not api_key or not api_secret or not passphrase:
                raise ValueError("OKX broker requires api_key, api_secret, passphrase")

            return OKXBroker(
                api_key=str(api_key),
                api_secret=str(api_secret),
                passphrase=str(passphrase),
                demo=config.get("demo", True),
                inst_suffix=config.get("inst_suffix", "USDT"),
            )

        else:
            raise ValueError(f"Unknown broker type: {broker_type}")

    @staticmethod
    def get_available_types() -> list[str]:
        return ["paper", "okx"]


class AdaptersProvider(Provider):
    broker_factory = provide(BrokerFactory, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_sync_policies(self, settings: Settings) -> SyncPolicies:
        return SyncPolicies(
            [
                binance_policy(
                    data_provider=BinanceClient(settings=settings),
                    quote_provider=BinanceWebSocketClient(),
                )
            ]
        )
