"""Dishka DI container factory."""

from dishka import AsyncContainer, make_async_container

from pocketquant.app.di import (
    AppTradingServiceProvider,
    BacktestWorkerProvider,
    CoreProvider,
    ExecutionProvider,
    InfrastructureProvider,
    MarketDataProvider,
    PersistenceProvider,
)

PROVIDERS = [
    CoreProvider(),
    PersistenceProvider(),
    InfrastructureProvider(),
    ExecutionProvider(),
    MarketDataProvider(),
    AppTradingServiceProvider(),
    BacktestWorkerProvider(),
]


def create_container() -> AsyncContainer:
    return make_async_container(*PROVIDERS)
