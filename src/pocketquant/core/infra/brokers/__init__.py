"""Broker infrastructure — concrete adapters (paper, Exness).

Ports + DTOs (IBrokerPort, IBrokerFactoryPort, OrderResult, AccountBalance, OrderEvent)
live in ``pocketquant.core.domain.brokers``. This package holds the concrete
PaperBrokerAdapter and ExnessBrokerAdapter adapters.
"""

from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

__all__ = ["PaperBrokerAdapter"]
