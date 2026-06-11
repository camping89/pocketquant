"""CQRS handler provider for bff — all backtest handlers migrated to BacktestCommandService
/ BacktestQueryService. This shell is retained so container.py import chain is
unchanged; it will be deleted when the Mediator itself is removed.
"""

from dishka import Provider


class BffHandlerProvider(Provider):
    # All handlers removed — backtest routes now call feature services directly.
    pass


ALL_BFF_HANDLER_TYPES: list[type] = []
