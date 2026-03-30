"""Handler for running a backtest."""

from pocketquant.backtest.domain import BacktestResult
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService


@handles(RunBacktestCommand)
class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResult]):
    """Handle RunBacktestCommand - execute a single backtest."""

    def __init__(
        self,
        event_bus: EventBus,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._event_bus = event_bus
        self._backtest_repo = backtest_repository
        self._bar_repo = bar_repository
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: RunBacktestCommand) -> BacktestResult:
        """Execute backtest and return result."""
        config = BacktestConfig(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            interval=request.interval,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            slippage_bps=request.slippage_bps,
            commission_bps=request.commission_bps,
            parameters=request.parameters or {},
        )

        # Resolve strategy class from registry
        strategy_class = STRATEGY_REGISTRY.get(request.strategy_id)
        if strategy_class is None:
            raise ValueError(
                f"Unknown strategy: '{request.strategy_id}'. "
                f"Available: {list(STRATEGY_REGISTRY.keys())}"
            )

        # Build StrategyConfig for this backtest run (parameters may be overridden)
        strategy_cfg = StrategyConfig(
            id=request.strategy_id,
            name=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            interval=request.interval,
            trigger="bar",
            broker="paper",
            parameters={**config.parameters},
        )

        # Create fresh broker for this backtest
        broker = PaperBroker(
            initial_balance=request.initial_capital,
            slippage_percent=config.slippage_percent,
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
        async with self._strategy_app_service._lock:
            self._strategy_app_service._strategies[sid] = strategy
            self._strategy_app_service._brokers[sid] = broker
            self._strategy_app_service._configs[sid] = strategy.config
            # Connect broker and start strategy inside the lock (broker is PaperBroker,
            # connect() is a no-op, so this is safe)
            if not broker.is_connected:
                await broker.connect()
            await strategy.on_start()
