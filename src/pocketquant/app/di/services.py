"""Services provider: app services, the execution engine and the feature services routes inject.

OrderAppService and PositionAppService need async post-init (load state from DB).
StrategyAppService uses a generator factory for start/stop lifecycle.
The ``/backtest/run`` route allocates a run id, persists the started doc, then
spawns ``BacktestExecutionService.execute_and_persist`` as an asyncio task.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper
from pocketquant.engine.backtest.backtest_command_service import BacktestCommandService
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.engine.backtest.backtest_query_service import BacktestQueryService
from pocketquant.engine.backtest.backtest_stats_service import BacktestStatsService
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.live.live_metrics_query_service import LiveMetricsQueryService
from pocketquant.engine.live.live_trade_collector import LiveTradeCollector
from pocketquant.engine.live.strategy_reconcile_app_service import (
    StrategyReconcileAppService,
)
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.engine.market_data.app_services.ws_subscription_app_service import (
    WsSubscriptionAppService,
)
from pocketquant.engine.market_data.data_lag_service import DataLagQueryService
from pocketquant.engine.market_data.ohlcv_service import OhlcvService
from pocketquant.engine.market_data.quotes_service import QuoteQueryService
from pocketquant.engine.market_data.symbols_service import SymbolQueryService
from pocketquant.engine.market_data.sync_service import SyncService
from pocketquant.engine.market_data.sync_status_service import SyncStatusQueryService
from pocketquant.engine.market_data.tracked_symbols_backfill import TrackedSymbolBackfillService
from pocketquant.engine.market_data.tracked_symbols_service import TrackedSymbolService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService
from pocketquant.engine.strategy.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy.strategy_query_service import StrategyQueryService


class ServicesProvider(Provider):
    # Market data. SyncService is also used by scheduler jobs (sync_1m,
    # sync_backfill, repair) directly.
    sync_service = provide(SyncService, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_bar_manager(
        self,
        cache: Cache,
        bar_repository: BarRepository,
        event_bus: EventBus,
        calendar_factory: TradingCalendarFactory,
    ) -> BarAppService:
        return BarAppService(
            cache=cache,
            bar_repository=bar_repository,
            event_bus=event_bus,
            calendar_factory=calendar_factory,
        )

    @provide(scope=Scope.APP)
    def get_quote_service(
        self,
        cache: Cache,
        bar_manager: BarAppService,
        provider: IRealtimeQuoteProviderPort,
    ) -> QuoteAppService:
        return QuoteAppService(cache=cache, bar_manager=bar_manager, provider=provider)

    @provide(scope=Scope.APP)
    def get_ws_subscription_manager(
        self,
        provider: IRealtimeQuoteProviderPort,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,
    ) -> WsSubscriptionAppService:
        return WsSubscriptionAppService(
            provider=provider,
            tracked_symbol_repo=tracked_symbol_repo,
            quote_app_service=quote_app_service,
        )

    # Execution engine and live trading.
    risk_handler = provide(RiskCheckHandler, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def get_order_manager(
        self, event_bus: EventBus, order_repository: OrderRepository
    ) -> OrderAppService:
        manager = OrderAppService(event_bus, order_repository)
        await manager.load_pending_orders()
        return manager

    @provide(scope=Scope.APP)
    async def get_position_tracker(
        self,
        event_bus: EventBus,
        position_repository: PositionRepository,
        subscription_repository: SubscriptionRepository,
        symbol_lookup: SymbolLookupHelper,
    ) -> PositionAppService:
        tracker = PositionAppService(event_bus, position_repository, symbol_lookup)
        subs = await subscription_repository.list_all()
        await tracker.start(frozenset(str(s.id) for s in subs if s.broker == "paper"))
        return tracker

    @provide(scope=Scope.APP)
    async def get_strategy_engine(
        self,
        event_bus: EventBus,
        broker_factory: BrokerFactory,
        order_app_service: OrderAppService,
        position_app_service: PositionAppService,
        risk_check_handler: RiskCheckHandler,
        settings: Settings,
        bar_repository: BarRepository,
        calendar_factory: TradingCalendarFactory,
        trade_repository: TradeRepository,
    ) -> AsyncIterator[StrategyAppService]:
        engine = StrategyAppService(
            event_bus=event_bus,
            broker_factory=broker_factory,
            order_app_service=order_app_service,
            position_app_service=position_app_service,
            risk_check_handler=risk_check_handler,
            default_broker_config={
                "initial_balance": settings.paper_initial_balance,
                "futures_initial_balance": settings.paper_futures_initial_balance,
                "slippage_bps": settings.paper_slippage_bps,
                "commission_bps": settings.paper_commission_bps,
            },
            bar_repository=bar_repository,
            calendar_factory=calendar_factory,
            trade_repository=trade_repository,
        )
        await engine.start()
        yield engine
        # A drained trader has no task left; this bounds every other shutdown.
        await engine.stop(timeout_s=5.0)

    @provide(scope=Scope.APP)
    def get_reconcile_service(
        self,
        subscription_repository: SubscriptionRepository,
        strategy_app_service: StrategyAppService,
        settings: Settings,
        symbol_lookup: SymbolLookupHelper,
        safeguards: Safeguards,
    ) -> StrategyReconcileAppService:
        return StrategyReconcileAppService(
            subscription_repository,
            strategy_app_service,
            interval_s=settings.reconcile_interval_seconds,
            symbol_lookup=symbol_lookup,
            exness_risk=RiskConfig(
                leverage=safeguards.leverage, risk_per_trade=safeguards.risk_per_trade
            ),
            futures_paper_risk=RiskConfig(leverage=settings.paper_futures_leverage),
        )

    @provide(scope=Scope.APP)
    def get_live_trade_collector(
        self,
        event_bus: EventBus,
        trade_repository: TradeRepository,
        strategy_app_service: StrategyAppService,
    ) -> LiveTradeCollector:
        return LiveTradeCollector(event_bus, trade_repository, strategy_app_service)

    @provide(scope=Scope.APP)
    def get_live_metrics_query_service(
        self,
        trade_repository: TradeRepository,
        settings: Settings,
        symbol_lookup: SymbolLookupHelper,
    ) -> LiveMetricsQueryService:
        return LiveMetricsQueryService(
            trade_repository,
            baseline=settings.paper_initial_balance,
            futures_baseline=settings.paper_futures_initial_balance,
            symbol_lookup=symbol_lookup,
        )

    # Backtest execution.
    backtest_execution_service = provide(BacktestExecutionService, scope=Scope.APP)

    # Feature services that routes inject directly.
    tracked_symbol_service = provide(TrackedSymbolService, scope=Scope.APP)
    tracked_symbol_backfill_service = provide(TrackedSymbolBackfillService, scope=Scope.APP)
    ohlcv_service = provide(OhlcvService, scope=Scope.APP)
    quote_query_service = provide(QuoteQueryService, scope=Scope.APP)
    sync_status_query_service = provide(SyncStatusQueryService, scope=Scope.APP)
    data_lag_query_service = provide(DataLagQueryService, scope=Scope.APP)
    symbol_query_service = provide(SymbolQueryService, scope=Scope.APP)
    backtest_command_service = provide(BacktestCommandService, scope=Scope.APP)
    backtest_query_service = provide(BacktestQueryService, scope=Scope.APP)
    backtest_stats_service = provide(BacktestStatsService, scope=Scope.APP)
    strategy_command_service = provide(StrategyCommandService, scope=Scope.APP)
    strategy_query_service = provide(StrategyQueryService, scope=Scope.APP)
