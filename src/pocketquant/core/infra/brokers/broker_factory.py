from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.core.domain.trading import commission_model_for
from pocketquant.core.infra.brokers.exness.exness_broker_adapter import ExnessBrokerAdapter
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.safeguards_repository import (
    SafeguardsRepository,
)


class BrokerFactory:
    """Factory for creating broker instances from configuration.

    Holds the application ``EventBus`` so paper brokers can subscribe to
    ``BarCompletedEvent`` and auto-fill SL/TP during live paper trading.
    Exness also takes the bus: its fills arrive from the venue and are published.
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        exness_client: ExnessClient | None = None,
        position_repository: PositionRepository | None = None,
        safeguards: Safeguards | None = None,
        safeguards_repository: SafeguardsRepository,
    ) -> None:
        self._event_bus = event_bus
        self._exness_client = exness_client
        self._position_repository = position_repository
        self._safeguards = safeguards
        self._safeguards_repository = safeguards_repository

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
        """Create broker instance from type and config.

        Args:
            broker_type: "paper" or "exness"
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
            contract_spec: ContractSpec = config.get("contract_spec") or LINEAR_SPEC
            # An explicit config fee wins; otherwise the symbol's spec decides.
            per_contract = config.get("commission_per_contract")
            if per_contract is None:
                per_contract = contract_spec.commission_per_contract
            initial_balance = config.get("initial_balance", 10_000.0)
            if contract_spec.is_contract and config.get("futures_initial_balance") is not None:
                initial_balance = config["futures_initial_balance"]
            return PaperBrokerAdapter(
                initial_balance=initial_balance,
                slippage_percent=slippage_bps / 10_000,
                fill_delay_ms=config.get("fill_delay_ms", 50),
                currency=config.get("currency", "USD"),
                event_bus=self._event_bus,
                commission_model=commission_model_for(per_contract, commission_bps),
                contract_spec=contract_spec,
            )

        elif broker_type == "exness":
            # The first of two locks: the client also refuses order calls while off.
            safeguards = self._safeguards
            if safeguards is None or not safeguards.live_trading:
                raise ValueError("exness broker is disabled: EXNESS_LIVE_TRADING is false")
            client = self._exness_client
            if client is None or not client.is_configured or self._position_repository is None:
                raise ValueError("exness broker requires EXNESS_* settings")
            return ExnessBrokerAdapter(
                client,
                self._event_bus,
                self._position_repository,
                safeguards,
                self._safeguards_repository,
            )

        else:
            raise ValueError(f"Unknown broker type: {broker_type}")
