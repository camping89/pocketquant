from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.trading import PercentageCommissionModel
from pocketquant.core.infra.brokers.okx.okx_broker_adapter import OKXBrokerAdapter
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter


class BrokerFactory:
    """Factory for creating broker instances from configuration.

    Holds the application ``EventBus`` so paper brokers can subscribe to
    ``BarCompletedEvent`` and auto-fill SL/TP during live paper trading.
    Real brokers (OKX) ignore the bus — they receive fills from the venue.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
        """Create broker instance from type and config.

        Args:
            broker_type: "paper" or "okx"
            config: Broker-specific configuration

        Returns:
            IBrokerPort instance

        Raises:
            ValueError: If broker type is unknown
        """
        if broker_type == "paper":
            # Config surfaces slippage + commission as bps; the adapter takes
            # slippage as a fraction, so convert here at the boundary.
            commission_bps = config.get("commission_bps", 0.0)
            slippage_bps = config.get("slippage_bps", 0.0)
            return PaperBrokerAdapter(
                initial_balance=config.get("initial_balance", 10_000.0),
                slippage_percent=slippage_bps / 10_000,
                fill_delay_ms=config.get("fill_delay_ms", 50),
                currency=config.get("currency", "USD"),
                event_bus=self._event_bus,
                commission_model=PercentageCommissionModel(bps=commission_bps),
            )

        elif broker_type == "okx":
            # Validate required OKX credentials
            api_key = config.get("api_key")
            api_secret = config.get("api_secret")
            passphrase = config.get("passphrase")

            if not api_key or not api_secret or not passphrase:
                raise ValueError("OKX broker requires api_key, api_secret, passphrase")

            return OKXBrokerAdapter(
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
