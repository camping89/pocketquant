"""CQRS handler provider for app — all backtest handlers migrated to feature services.

The backtest worker (BacktestRequestWorker) calls backtest_dispatch directly; it
does not go through the Mediator. This shell is retained so container.py and the
mediator registry contract test import chain are unchanged; it will be deleted
when the Mediator itself is removed.
"""

from dishka import Provider


class HandlerProvider(Provider):
    # All handlers removed — worker dispatches via backtest_dispatch directly.
    pass


ALL_HANDLER_TYPES: list[type] = []
