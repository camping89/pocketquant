"""Broker factory for creating broker instances."""

from src.infrastructure.brokers.interface import IBroker
from src.infrastructure.brokers.okx.okx_broker import OKXBroker
from src.infrastructure.brokers.paper.paper_broker import PaperBroker


class BrokerFactory:
    """Factory for creating broker instances from configuration."""

    @staticmethod
    def create(broker_type: str, config: dict) -> IBroker:
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
            )

        elif broker_type == "okx":
            # Validate required OKX credentials
            api_key = config.get("api_key")
            api_secret = config.get("api_secret")
            passphrase = config.get("passphrase")

            if not all([api_key, api_secret, passphrase]):
                raise ValueError("OKX broker requires api_key, api_secret, passphrase")

            return OKXBroker(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                demo=config.get("demo", True),
                inst_suffix=config.get("inst_suffix", "USDT"),
            )

        else:
            raise ValueError(f"Unknown broker type: {broker_type}")

    @staticmethod
    def get_available_types() -> list[str]:
        """Get list of available broker types."""
        return ["paper", "okx"]
