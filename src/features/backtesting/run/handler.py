"""Handler for running a backtest."""


from src.application.backtesting.backtest_runner import BacktestRunner
from src.application.backtesting.models.backtest_config import BacktestConfig
from src.application.backtesting.models.backtest_result import BacktestResult
from src.application.strategy.strategy_engine import StrategyEngine
from src.common.mediator import Handler, handles
from src.common.messaging import EventBus
from src.features.backtesting.run.command import RunBacktestCommand
from src.infrastructure.brokers.paper.paper_broker import PaperBroker
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository


@handles(RunBacktestCommand)
class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResult]):
    """Handle RunBacktestCommand - execute a single backtest."""

    def __init__(
        self,
        event_bus: EventBus,
        strategy_engine: StrategyEngine,
        backtest_repository: BacktestRepository,
        ohlcv_repository: OHLCVRepository,
    ) -> None:
        self._event_bus = event_bus
        self._strategy_engine = strategy_engine
        self._backtest_repo = backtest_repository
        self._ohlcv_repo = ohlcv_repository

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

        # Create fresh broker for this backtest
        broker = PaperBroker(
            initial_balance=request.initial_capital,
            slippage_percent=config.slippage_percent,
        )

        runner = BacktestRunner(
            event_bus=self._event_bus,
            strategy_engine=self._strategy_engine,
            broker=broker,
            backtest_repository=self._backtest_repo,
            ohlcv_repository=self._ohlcv_repo,
        )

        return await runner.run(config)
