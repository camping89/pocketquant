from typing import Protocol

from pocketquant.core.domain.brokers.broker_port import IBrokerPort


class IBrokerFactoryPort(Protocol):
    def create(self, broker_type: str, config: dict) -> IBrokerPort: ...
