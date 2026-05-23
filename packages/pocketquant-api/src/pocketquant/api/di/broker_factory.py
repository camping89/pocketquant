"""Broker factory for creating broker instances."""

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.infrastructure.brokers.interface import IBroker
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.trading.brokers.okx.okx_broker import OKXBroker


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
        """Get list of available broker types."""
        return ["paper", "okx"]
