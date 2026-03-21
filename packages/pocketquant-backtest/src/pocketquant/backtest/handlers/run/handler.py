"""Handler for running a backtest."""

from pocketquant.backtest.domain import BacktestResult
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.persistence.repositories.bar_repository import BarRepository


@handles(RunBacktestCommand)
class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResult]):
    """Handle RunBacktestCommand - execute a single backtest."""

    def __init__(
        self,
        event_bus: EventBus,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
    ) -> None:
        self._event_bus = event_bus
        self._backtest_repo = backtest_repository
        self._bar_repo = bar_repository

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

        runner = BacktestAppService(
            event_bus=self._event_bus,
            broker=broker,
            backtest_repository=self._backtest_repo,
            bar_repository=self._bar_repo,
        )

        return await runner.run(config)
