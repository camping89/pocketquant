"""Feature-service provider for bff — services routes inject directly.

Replaces per-endpoint CQRS handlers: each feature area exposes one service
class; routes call its methods via FromDishka injection.
"""

from dishka import Provider, Scope, provide

from pocketquant.backtest.backtest_command_service import BacktestCommandService
from pocketquant.backtest.backtest_query_service import BacktestQueryService
from pocketquant.engine.market_data.ohlcv_service import OhlcvService
from pocketquant.engine.market_data.quotes_service import QuoteQueryService
from pocketquant.engine.market_data.symbols_service import SymbolQueryService
from pocketquant.engine.market_data.sync_service import SyncService
from pocketquant.engine.market_data.sync_status_service import SyncStatusQueryService
from pocketquant.engine.market_data.tracked_symbols_backfill import TrackedSymbolBackfillService
from pocketquant.engine.market_data.tracked_symbols_service import TrackedSymbolService
from pocketquant.engine.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy_query_service import StrategyQueryService


class BffServiceProvider(Provider):
    tracked_symbol_service = provide(TrackedSymbolService, scope=Scope.APP)
    tracked_symbol_backfill_service = provide(TrackedSymbolBackfillService, scope=Scope.APP)
    sync_service = provide(SyncService, scope=Scope.APP)
    ohlcv_service = provide(OhlcvService, scope=Scope.APP)
    quote_query_service = provide(QuoteQueryService, scope=Scope.APP)
    sync_status_query_service = provide(SyncStatusQueryService, scope=Scope.APP)
    symbol_query_service = provide(SymbolQueryService, scope=Scope.APP)
    strategy_command_service = provide(StrategyCommandService, scope=Scope.APP)
    strategy_query_service = provide(StrategyQueryService, scope=Scope.APP)
    backtest_command_service = provide(BacktestCommandService, scope=Scope.APP)
    backtest_query_service = provide(BacktestQueryService, scope=Scope.APP)
