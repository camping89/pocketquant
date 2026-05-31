from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.infrastructure.persistence.repositories.backtest_order_repository import BacktestOrderRepository
from pocketquant.infrastructure.persistence.repositories.backtest_repository import BacktestRepository
from pocketquant.infrastructure.persistence.repositories.backtest_trade_repository import BacktestTradeRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService


@handles(RunBacktestCommand)
class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResult]):
    def __init__(
        self,
        event_bus: EventBus,
        backtest_repository: BacktestRepository,
        backtest_order_repository: BacktestOrderRepository,
        backtest_trade_repository: BacktestTradeRepository,
        bar_repository: BarRepository,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._event_bus = event_bus
        self._backtest_repo = backtest_repository
        self._order_repo = backtest_order_repository
        self._trade_repo = backtest_trade_repository
        self._bar_repo = bar_repository
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: RunBacktestCommand) -> BacktestResult:
        config = BacktestConfig(
            strategy_code=request.strategy_id,
            symbol=request.symbol,
            interval=request.interval,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            slippage_bps=request.slippage_bps,
            commission_bps=request.commission_bps,
            parameters=request.parameters or {},
        )

        strategy_class = STRATEGY_REGISTRY.get(request.strategy_id)
        if strategy_class is None:
            raise ValueError(
                f"Unknown strategy: '{request.strategy_id}'. "
                f"Available: {list(STRATEGY_REGISTRY.keys())}"
            )

        strategy_cfg = StrategyConfig(
            id=request.strategy_id,
            name=request.strategy_id,
            symbol=request.symbol,
            interval=request.interval,
            trigger="bar",
            broker="paper",
            parameters={**config.parameters},
        )

        # Create fresh broker for this backtest. event_bus enables SL/TP auto-fill
        # on BarCompletedEvent — required for strategies that set sl_price/tp_price.
        broker = PaperBroker(
            initial_balance=request.initial_capital,
            slippage_percent=config.slippage_percent,
            event_bus=self._event_bus,
        )

        # Register strategy instance on the shared StrategyAppService so it
        # receives BarCompletedEvent during replay
        strategy_instance = strategy_class(strategy_cfg)
        await self._load_strategy_for_backtest(strategy_instance, broker)

        try:
            runner = BacktestAppService(
                event_bus=self._event_bus,
                broker=broker,
                backtest_repository=self._backtest_repo,
                bar_repository=self._bar_repo,
                order_repository=self._order_repo,
                trade_repository=self._trade_repo,
            )
            return await runner.run(config)
        finally:
            # Clean up: unload backtest strategy so it doesn't linger
            await self._strategy_app_service.unload_strategy(request.strategy_id)

    async def _load_strategy_for_backtest(self, strategy, broker) -> None:
        """Inject strategy + broker directly into StrategyAppService internals."""
        sid = strategy.id
        # Unload any stale previous run with the same ID
        if self._strategy_app_service.get_strategy(sid) is not None:
            await self._strategy_app_service.unload_strategy(sid)

        # Inject directly — bypass load_strategy() to avoid broker-factory lookup.
        # start_strategy() also acquires _lock; do both in one critical section.
        async with self._strategy_app_service._lock:  # pyright: ignore[reportPrivateUsage]
            self._strategy_app_service._strategies[sid] = strategy  # pyright: ignore[reportPrivateUsage]
            self._strategy_app_service._brokers[sid] = broker  # pyright: ignore[reportPrivateUsage]
            self._strategy_app_service._configs[sid] = strategy.config  # pyright: ignore[reportPrivateUsage]
            # Connect broker and start strategy inside the lock (broker is PaperBroker,
            # connect() is a no-op, so this is safe)
            if not broker.is_connected:
                await broker.connect()
            await strategy.on_start()
