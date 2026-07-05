"""Broker infrastructure — concrete adapters (paper, OKX).

Ports + DTOs (IBrokerPort, IBrokerFactoryPort, OrderResult, AccountBalance, OrderEvent)
live in ``pocketquant.core.domain.brokers``. This package holds the concrete
PaperBrokerAdapter and OKXBrokerAdapter adapters.
"""

from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

__all__ = ["PaperBrokerAdapter"]
