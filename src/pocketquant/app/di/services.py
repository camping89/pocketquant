"""Feature-service provider — services that routes inject directly.

Replaces per-endpoint CQRS handlers: each feature area exposes one service
class; routes call its methods via FromDishka injection.

StrategyCommandService / StrategyQueryService / SyncService are NOT provided
here — they live in AppTradingServiceProvider and MarketDataProvider. Dishka
silently lets the last duplicate registration win, so every type must have
exactly one provider.
"""

from dishka import Provider, Scope, provide

from pocketquant.engine.backtest.backtest_command_service import BacktestCommandService
from pocketquant.engine.backtest.backtest_query_service import BacktestQueryService
from pocketquant.engine.backtest.backtest_stats_service import BacktestStatsService
from pocketquant.engine.market_data.ohlcv_service import OhlcvService
from pocketquant.engine.market_data.quotes_service import QuoteQueryService
from pocketquant.engine.market_data.symbols_service import SymbolQueryService
from pocketquant.engine.market_data.sync_status_service import SyncStatusQueryService
from pocketquant.engine.market_data.tracked_symbols_backfill import TrackedSymbolBackfillService
from pocketquant.engine.market_data.tracked_symbols_service import TrackedSymbolService


class ServicesProvider(Provider):
    tracked_symbol_service = provide(TrackedSymbolService, scope=Scope.APP)
    tracked_symbol_backfill_service = provide(TrackedSymbolBackfillService, scope=Scope.APP)
    ohlcv_service = provide(OhlcvService, scope=Scope.APP)
    quote_query_service = provide(QuoteQueryService, scope=Scope.APP)
    sync_status_query_service = provide(SyncStatusQueryService, scope=Scope.APP)
    symbol_query_service = provide(SymbolQueryService, scope=Scope.APP)
    backtest_command_service = provide(BacktestCommandService, scope=Scope.APP)
    backtest_query_service = provide(BacktestQueryService, scope=Scope.APP)
    backtest_stats_service = provide(BacktestStatsService, scope=Scope.APP)
