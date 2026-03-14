"""Manually trigger scheduled sync jobs without waiting for APScheduler.

These jobs (_sync_all_symbols, _sync_daily_data) normally fire on cron/interval
and are NOT exposed via REST API. This is the only way to invoke them on-demand
for debugging or verifying sync logic after changes.

Requires: `just up` + at least one previously synced symbol.

Usage:
    python testscripts/run_sync_jobs.py
"""

import asyncio
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.market_data.sync_jobs import _sync_all_symbols, _sync_daily_data
from src.common.mediator.mediator import Mediator
from src.common.messaging import EventBus
from src.config import get_settings
from src.infrastructure.tradingview import TradingViewClient
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository


async def main() -> None:
    print("=" * 50)
    print("Triggering Scheduled Sync Jobs")
    print("=" * 50)

    settings = get_settings()

    # Init persistence
    database = Database()
    await database.connect(settings)
    cache = Cache()
    await cache.connect(settings)

    try:
        # Build minimal deps needed for sync jobs
        sync_status_repo = SyncStatusRepository(database=database)
        mediator = Mediator()

        # Register sync handler so mediator can dispatch
        from src.handler_registration import register_all_handlers
        from src.services import Services

        ohlcv_repo = OHLCVRepository(database=database)
        symbol_repo = SymbolRepository(database=database)
        event_bus = EventBus(max_history=100)

        # Build minimal Services (only fields needed for sync handlers)
        from src.application.market_data.bar_app_service import BarAppService
        from src.application.market_data.quote_app_service import QuoteAppService
        from src.application.strategy.strategy_app_service import StrategyAppService
        from src.application.trading.order_app_service import OrderAppService
        from src.application.trading.position_app_service import PositionAppService
        from src.common.health import HealthCoordinator
        from src.features.risk.check_risk.handler import RiskCheckHandler
        from src.infrastructure.brokers import BrokerFactory
        from src.infrastructure.scheduling.scheduler import JobScheduler
        from src.persistence.repositories.backtest_repository import (
            BacktestRepository,
        )
        from src.persistence.repositories.optimization_repository import (
            OptimizationRepository,
        )
        from src.persistence.repositories.order_repository import OrderRepository
        from src.persistence.repositories.position_repository import (
            PositionRepository,
        )

        order_repo = OrderRepository(database=database)
        position_repo = PositionRepository(database=database)
        order_manager = OrderAppService(event_bus, order_repo)
        position_tracker = PositionAppService(event_bus, position_repo)

        services = Services(
            settings=settings,
            database=database,
            cache=cache,
            order_repository=order_repo,
            position_repository=position_repo,
            backtest_repository=BacktestRepository(database=database),
            ohlcv_repository=ohlcv_repo,
            symbol_repository=symbol_repo,
            sync_status_repository=sync_status_repo,
            optimization_repository=OptimizationRepository(database=database),
            event_bus=event_bus,
            mediator=mediator,
            job_scheduler=JobScheduler(),
            tv_provider=TradingViewClient(settings=settings),
            broker_factory=BrokerFactory(),
            risk_handler=RiskCheckHandler(),
            health_coordinator=HealthCoordinator(timeout=5.0),
            bar_manager=BarAppService(cache=cache, ohlcv_repository=ohlcv_repo),
            quote_service=QuoteAppService(
                settings=settings,
                cache=cache,
                bar_manager=BarAppService(cache=cache, ohlcv_repository=ohlcv_repo),
            ),
            order_manager=order_manager,
            position_tracker=position_tracker,
            strategy_engine=StrategyAppService(
                event_bus=event_bus,
                broker_factory=BrokerFactory(),
                order_manager=order_manager,
                position_tracker=position_tracker,
                risk_handler=RiskCheckHandler(),
                default_broker_config={},
            ),
        )
        register_all_handlers(services)

        print("\n[1] _sync_daily_data (1d interval symbols, 10 bars each)...")
        try:
            await _sync_daily_data(mediator, sync_status_repo)
            print("    [OK] completed")
        except Exception as e:
            print(f"    [WARN] {e}")

        print("\n[2] _sync_all_symbols (ALL tracked symbols, 500 bars each)...")
        try:
            await _sync_all_symbols(mediator, sync_status_repo)
            print("    [OK] completed")
        except Exception as e:
            print(f"    [WARN] {e}")

    finally:
        await cache.disconnect()
        await database.disconnect()

    print("\n" + "=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
