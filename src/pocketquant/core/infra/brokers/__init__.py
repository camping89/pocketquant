"""Broker infrastructure — concrete adapters (paper, OKX).

Ports + DTOs (IBroker, IBrokerFactory, OrderResult, AccountBalance, OrderEvent)
live in ``pocketquant.core.domain.brokers``. This package holds the concrete
PaperBroker and OKXBroker adapters.
"""

from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker

__all__ = ["PaperBroker"]
