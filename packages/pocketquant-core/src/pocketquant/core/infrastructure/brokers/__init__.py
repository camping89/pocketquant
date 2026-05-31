"""Broker infrastructure — paper implementation.

Ports + DTOs (IBroker, IBrokerFactory, OrderResult, AccountBalance, OrderEvent)
live in ``pocketquant.core.domain.brokers``. This package holds only the
concrete PaperBroker adapter.
"""

from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker

__all__ = ["PaperBroker"]
