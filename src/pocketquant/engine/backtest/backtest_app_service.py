import asyncio
from datetime import UTC, datetime
from time import perf_counter

import structlog

from pocketquant.core.common.logging import BACKTEST_RUN_ID, get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.backtest import BacktestConfig, BacktestResult
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.backtest.backtest_report_app_service import BacktestReportAppService

logger = get_logger(__name__)

# Yield to the event loop every N bars so a multi-hundred-thousand-bar run can't
# starve the WS feed / reconcile loop / health checks sharing this process.
_YIELD_EVERY = 10


class BacktestAppService:
    """Runs one backtest: replays stored bars on the bus, then persists the report.

    Each bar sets the broker price and the simulation time, then is published as
    a ``BarCompletedEvent``. The run, its orders and its trades are persisted in
    the order orders → trades → run.
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker: PaperBrokerAdapter,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
        calendar: ITradingCalendarPort,
        order_repository: BacktestOrderRepository,
        trade_repository: BacktestTradeRepository,
    ) -> None:
        self._event_bus = event_bus
        self._broker = broker
        self._backtest_repo = backtest_repository
        self._order_repo = order_repository
        self._trade_repo = trade_repository
        self._bar_repo = bar_repository
        self._calendar = calendar

    async def run(self, config: BacktestConfig, run_id: str | None = None) -> BacktestResult:
        """Execute a single backtest run with full metrics collection.

        ``run_id`` is allocated by the caller (the route) so the started doc, the
        finished doc, and every persisted order/trade share one id; a caller
        without a started doc leaves it None and one is allocated here.

        Returns the slim BacktestResult (metrics + equity_curve + open_positions);
        Orders and Trades are persisted to ``backtest_orders`` and ``backtest_trades``
        respectively and must be queried via their dedicated repositories.
        """
        run_id = run_id or generate_id_str()
        started_at = datetime.now(UTC)

        logger.info(
            "backtest_starting",
            run_id=run_id,
            strategy_code=config.strategy_code,
            symbol=config.symbol,
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
        )

        collector = BacktestReportAppService(
            config,
            config.initial_capital,
            broker=self._broker,
            calendar=self._calendar,
            run_id=run_id,
        )

        # Mark-to-market per bar for an evenly-sampled equity curve (Sharpe
        # input). Registered AFTER the broker's BarCompletedEvent handler
        # (subscribed in broker.connect during strategy injection), so the equity
        # snapshot is taken once the bar's SL/TP exits have settled.
        async def _mtm_on_bar(event: BarCompletedEvent) -> None:
            if event.bar_start is None:
                return
            balance = await self._broker.get_balance()
            collector.mark_to_market(event.bar_start, balance.total_equity)

        try:
            self._broker.reset()
            self._broker.slippage = config.slippage_percent

            # Three channels: fills (OrderRecord + commission), events (audit log),
            # trades (round-trip closures for Trade-building + realized pnl).
            await self._broker.subscribe_order_updates(collector.on_fill)
            await self._broker.subscribe_order_event(collector.on_event)
            await self._broker.subscribe_trades(collector.on_trade)
            self._event_bus.subscribe(BarCompletedEvent, _mtm_on_bar)

            replay_started = perf_counter()
            bars_processed = 0
            with structlog.contextvars.bound_contextvars(**{BACKTEST_RUN_ID: run_id}):
                # ``stream`` is end-inclusive (``$lte end``), so a minute-precise
                # end keeps the bar at that exact minute and excludes later bars.
                async for bar in self._bar_repo.stream(
                    config.symbol, Interval(config.interval), config.start_date, config.end_date
                ):
                    self._broker.set_current_price(config.symbol, bar.close)
                    if bar.datetime is None:
                        continue
                    set_simulation_time(bar.datetime)
                    await self._event_bus.publish(
                        BarCompletedEvent(
                            symbol=bar.symbol,
                            interval=config.interval,
                            bar_start=bar.datetime,
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=bar.volume,
                            # Sim time, so the broker's same-bar rule compares like with like.
                            occurred_at=bar.datetime,
                        )
                    )
                    bars_processed += 1
                    if bars_processed % _YIELD_EVERY == 0:
                        await asyncio.sleep(0)

            completed_at = datetime.now(UTC)

            positions = await self._broker.get_positions()
            collected = await collector.finalize(
                started_at=started_at,
                completed_at=completed_at,
                status="finished",
                positions=positions,
            )

            logger.info(
                "backtest_completed",
                run_id=run_id,
                bars=bars_processed,
                replay_sec=round(perf_counter() - replay_started, 2),
                trades=collected.run.metrics.total_trades,
                orders=len(collected.orders),
                sharpe=round(collected.run.metrics.sharpe_ratio, 2),
                return_pct=round(collected.run.metrics.total_return * 100, 2),
            )

            # Order matters: orders → trades → run.
            await self._order_repo.save_many(collected.orders)
            await self._trade_repo.save_many(collected.trades)
            await self._backtest_repo.save(collected.run)

            return collected.run

        except Exception as e:
            completed_at = datetime.now(UTC)
            logger.error("backtest_failed", run_id=run_id, error=str(e))

            positions = await self._broker.get_positions()
            collected = await collector.finalize(
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                error_message=str(e),
                positions=positions,
            )

            # Best-effort partial persistence for audit trail
            try:
                await self._order_repo.save_many(collected.orders)
                await self._trade_repo.save_many(collected.trades)
            except Exception as persist_err:  # noqa: BLE001
                logger.warning("backtest_partial_persist_failed", error=str(persist_err))
            await self._backtest_repo.save(collected.run)

            return collected.run

        finally:
            await self._broker.unsubscribe_order_updates()
            await self._broker.unsubscribe_order_event()
            await self._broker.unsubscribe_trades()
            self._event_bus.unsubscribe(BarCompletedEvent, _mtm_on_bar)
            clear_simulation_time()
