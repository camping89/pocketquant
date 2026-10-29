import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING

import structlog

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.broker_factory_port import IBrokerFactoryPort
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderSide,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate, PositionSide, TradeClosedEvent
from pocketquant.core.domain.risk import PositionCalculatorDomainService
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from pocketquant.core.domain.symbol import ContractSpec
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

if TYPE_CHECKING:
    from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
    from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
    from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
    from pocketquant.engine.execution.order_app_service import OrderAppService
    from pocketquant.engine.execution.position_app_service import PositionAppService
    from pocketquant.engine.execution.risk_check import RiskCheckHandler

logger = structlog.get_logger(__name__)

# Stop distance used for sizing when a signal carries no stop-loss price.
_FALLBACK_SL_PCT = 0.01
# A live bar older than this (seconds after its end) is too late for an entry.
_STALE_AFTER_S = {"1m": 10, "5m": 30, "15m": 60, "1h": 120, "4h": 300, "1d": 600, "1w": 600}
# Stored bars replayed into a strategy when it starts.
_WARMUP_BARS = 500
# sync_1m stores the last closed 1m bar at second 12; a start before second 20 waits for it.
_WARMUP_READY_SECOND = 20


def _direction_of(position: PositionAggregate | None) -> Direction | None:
    if position is None:
        return None
    return Direction.LONG if position.side == PositionSide.LONG else Direction.SHORT


class StrategyAppService:
    """Engine for managing and executing trading strategies.

    Subscribes to market events and dispatches to registered strategies.
    Coordinates signal processing through risk checks and order submission.
    Warm-up reads the bar repository, the successor check the calendar, the paper
    restore the trade repository; the backtest sandbox passes no-op versions.
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker_factory: IBrokerFactoryPort,
        order_app_service: OrderAppService,
        position_app_service: PositionAppService,
        risk_check_handler: RiskCheckHandler,
        default_broker_config: dict | None = None,
        *,
        bar_repository: BarRepository,
        calendar_factory: TradingCalendarFactory,
        trade_repository: TradeRepository,
    ) -> None:
        self._event_bus = event_bus
        self._broker_factory = broker_factory
        self._order_app_service = order_app_service
        self._position_app_service = position_app_service
        self._risk_check_handler = risk_check_handler
        self._default_broker_config = default_broker_config or {}
        self._bar_repository = bar_repository
        self._calendar_factory = calendar_factory
        self._trade_repository = trade_repository

        self._strategies: dict[str, IStrategyService] = {}
        self._brokers: dict[str, IBrokerPort] = {}
        # Paper pools per contract spec (it prices every fill with one spec, so an
        # XAUUSD subscription cannot share the crypto paper account); a venue broker
        # pools per type, with no spec in its key.
        self._broker_pool: dict[tuple[str, ContractSpec | None], IBrokerPort] = {}
        self._configs: dict[str, StrategyConfig] = {}
        self._running = False
        self._lock = asyncio.Lock()

        # None = no new entry (standby, drained or lease lost): signals are discarded.
        # Before roles exist every engine trades.
        self.trading_until: datetime | None = datetime.max.replace(tzinfo=UTC)
        self._signal_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_bar_start: dict[str, datetime] = {}
        # _on_bar_completed calls still running, inline paper fills included; the trader
        # hands over at 0.
        self._running_bar_handlers = 0
        # Subscriptions whose signal reached the broker call; a lost lease never cancels those.
        self._sending: set[str] = set()
        # Why a None switch discards: standby before take_over(), drain after it, lease
        # after cancel_pending_signals().
        self._discard_reason = "standby"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Subscribe handlers to the event bus and mark running.

        A broker subscribes to ``BarCompletedEvent`` when it connects, which is
        after this, so strategies see a bar before the broker checks SL/TP.
        """
        if self._running:
            return

        self._event_bus.subscribe(BarCompletedEvent, self._on_bar_completed)
        self._event_bus.subscribe(OrderCancelledEvent, self._on_order_cancelled)
        self._event_bus.subscribe(OrderFilledEvent, self._on_order_filled)
        self._running = True

        logger.info("strategy_engine_started")

    async def stop(self, timeout_s: float) -> None:
        """Waits at most ``timeout_s`` for signal tasks: the caller passes what is left of its
        shutdown grace."""
        if not self._running:
            return

        pending = [t for t in self._signal_tasks.values() if not t.done()]
        if pending:
            _, late = await asyncio.wait(pending, timeout=max(timeout_s, 0.0))
            for task in late:
                task.cancel()
            if late:
                logger.error("strategy_engine.stop_timeout", pending=len(late))

        for strategy_id in list(self._strategies.keys()):
            await self.stop_strategy(strategy_id)

        for broker in self._brokers.values():
            await broker.disconnect()

        self._running = False
        logger.info("strategy_engine_stopped")

    async def take_over(self) -> None:
        """Load what a trading process owns and connect its brokers. Runs once per process,
        before bars flow."""
        async with self._lock:
            await self._order_app_service.load_pending_orders()
            await self._position_app_service.load_open_positions()
            restored = dropped = 0
            papers = {id(b): b for b in self._brokers.values() if isinstance(b, PaperBrokerAdapter)}
            for broker in papers.values():
                ids = [sid for sid, b in self._brokers.items() if b is broker]
                rows = []
                for sid in ids:
                    row = self._position_app_service.get(sid)
                    if row is None:
                        continue
                    if row.sl_price is None and row.tp_price is None:
                        logger.warning(
                            "paper_position_dropped_no_exits",
                            subscription_id=sid,
                            symbol=row.symbol,
                        )
                        await self._position_app_service.drop(sid)
                        dropped += 1
                        continue
                    rows.append(row)
                realized = await self._trade_repository.realized_net(ids)
                broker.restore(rows, realized)
                restored += len(rows)

            for sid, strategy in self._strategies.items():
                if not strategy.is_running:
                    continue
                strategy.restore_direction(_direction_of(self._position_app_service.get(sid)))
                broker = self._brokers[sid]
                if not broker.is_connected:
                    await broker.connect()
            # From now on a None switch means a drain, unless a lost lease marks it.
            self._discard_reason = "drain"
            logger.info(
                "strategy_engine.took_over",
                strategies=len(self._strategies),
                paper_brokers=len(papers),
                paper_positions=restored,
                paper_dropped=dropped,
            )

    async def load_strategy(
        self,
        config: StrategyConfig,
        strategy_class: type[IStrategyService] | None = None,
    ) -> str:
        """Load a strategy from configuration.

        Args:
            config: Strategy configuration
            strategy_class: Optional custom strategy class

        Returns:
            Strategy ID
        """
        async with self._lock:
            if config.id in self._strategies:
                raise ValueError(f"Strategy already loaded: {config.id}")

            broker = await self._get_or_create_broker(config.broker, config.contract_spec)

            if strategy_class:
                strategy = strategy_class(config)
            else:
                strategy = _DefaultStrategy(config)

            self._strategies[config.id] = strategy
            self._brokers[config.id] = broker
            self._configs[config.id] = config

            logger.info(
                "strategy_loaded",
                strategy_id=config.id,
                symbol=config.symbol,
                broker=config.broker,
            )

            return config.id

    async def start_strategy(self, strategy_id: str) -> None:
        """Start a strategy warmed up from up to 500 stored bars, with its stored direction.

        Signals of replayed bars are rejected, never sent. A standby engine does not
        connect the broker.
        """
        async with self._lock:
            if strategy_id not in self._strategies:
                raise ValueError(f"Strategy not found: {strategy_id}")

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                return

            broker = self._brokers[strategy_id]
            now = get_current_time()
            trading = self.trading_until is not None and now < self.trading_until
            if trading and not broker.is_connected:
                await broker.connect()

            config = strategy.config
            interval = Interval(config.interval)
            step = timedelta(seconds=INTERVAL_SECONDS[config.interval])
            calendar = await self._calendar_factory.for_symbol(config.symbol)
            bars = await self._closed_bars(config.symbol, interval, step, now)
            last = bars[-1].datetime if bars else None
            if (
                now.second < _WARMUP_READY_SECOND
                and last is not None
                and last + step < calendar.bar_start(now, interval)
            ):
                await asyncio.sleep(_WARMUP_READY_SECOND - now.second - now.microsecond / 1e6)
                now = get_current_time()
                bars = await self._closed_bars(config.symbol, interval, step, now)
                last = bars[-1].datetime if bars else None

            # No I/O from here to the direction restore.
            await strategy.on_start()
            for stored in bars:
                signal = await strategy.on_bar_completed(
                    {
                        "symbol": config.symbol,
                        "interval": config.interval,
                        "open": stored.open,
                        "high": stored.high,
                        "low": stored.low,
                        "close": stored.close,
                        "volume": stored.volume,
                        "timestamp": stored.datetime,
                    }
                )
                if signal:
                    await strategy.on_order_rejected("warmup")
            if last is not None:
                self._last_bar_start[strategy_id] = last
            else:
                self._last_bar_start.pop(strategy_id, None)
            strategy.restore_direction(_direction_of(self._position_app_service.get(strategy_id)))

            if last is not None:
                current = calendar.bar_start(now, interval)
                if calendar.trading_minutes(last + step, current):
                    logger.warning(
                        "strategy.warmup_incomplete",
                        subscription_id=strategy_id,
                        last_bar_start=last.isoformat(),
                        current_bucket_start=current.isoformat(),
                    )

            logger.info("strategy_started", strategy_id=strategy_id, warmup_bars=len(bars))

    async def _closed_bars(
        self, symbol: str, interval: Interval, step: timedelta, now: datetime
    ) -> list[Bar]:
        """Stored bars that closed by ``now``, oldest first."""
        found = await self._bar_repository.find(symbol, interval, end_date=now, limit=_WARMUP_BARS)
        return [b for b in reversed(found) if b.datetime is not None and b.datetime + step <= now]

    async def stop_strategy(self, strategy_id: str) -> None:
        async with self._lock:
            if strategy_id not in self._strategies:
                return

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                await strategy.on_stop()

            logger.info("strategy_stopped", strategy_id=strategy_id)

    async def unload_strategy(self, strategy_id: str) -> None:
        """Stop and forget a strategy, and retire what only it held.

        A paper broker simulates the position, so the subscription's position is
        dropped and a broker with no other holder is disconnected; otherwise it
        keeps checking SL/TP for no one. A venue keeps its position under its own
        SL/TP, so that one is only logged.
        """
        await self.stop_strategy(strategy_id)

        async with self._lock:
            self._strategies.pop(strategy_id, None)
            broker = self._brokers.pop(strategy_id, None)
            self._configs.pop(strategy_id, None)
            self._last_bar_start.pop(strategy_id, None)

            if isinstance(broker, PaperBrokerAdapter):
                dropped = broker.drop_positions(strategy_id)
                await self._position_app_service.drop(strategy_id)
                if not any(b is broker for b in self._brokers.values()):
                    await broker.disconnect()
                logger.info("strategy_unloaded", strategy_id=strategy_id, positions_dropped=dropped)
            else:
                logger.info("strategy_unloaded", strategy_id=strategy_id)
                if broker is not None and self._position_app_service.get(strategy_id):
                    logger.warning(
                        "strategy_unloaded_venue_position_kept",
                        strategy_id=strategy_id,
                        broker=broker.name,
                    )

    async def inject_prepared_strategy(
        self,
        sid: str,
        strategy: IStrategyService,
        broker: IBrokerPort,
        config: StrategyConfig,
    ) -> None:
        """Register an externally-prepared strategy+broker pair under ``sid``.

        Backtest callers build their own PaperBrokerAdapter and strategy instance (to
        bypass the broker-factory lookup) and inject them directly. Registration,
        broker connection, and ``on_start()`` MUST all happen inside the same
        critical section: ``start_strategy`` also takes ``_lock``, so a lock-split
        would race ``unload_strategy`` and could leave a strategy registered but
        never started, or a broker never connected (silent zero-trade backtests).
        """
        async with self._lock:
            self._strategies[sid] = strategy
            self._brokers[sid] = broker
            self._configs[sid] = config
            if not broker.is_connected:
                await broker.connect()
            await strategy.on_start()

    def get_config(self, sid: str) -> StrategyConfig | None:
        """Return the in-memory StrategyConfig registered under ``sid`` (or None).

        ``sid`` is the registration key — a live ``strategy_code`` for the
        subscription-backtest read path, or a synthetic per-job id for injected
        backtests. Caller picks the keyspace.
        """
        return self._configs.get(sid)

    def get_strategy(self, strategy_id: str) -> IStrategyService | None:
        return self._strategies.get(strategy_id)

    def loaded_strategy_ids(self) -> list[str]:
        """Return all currently-loaded instance keys (snapshot, lock-free read).

        Keys are subscription ids in the live engine and strategy codes in a
        backtest sandbox; each engine only ever holds one kind.
        """
        return list(self._strategies.keys())

    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        """Feed the bar to each matching strategy and send its signal unless a guard skips it.

        A bar already seen is ignored. An entry on a stale, gapped or non-successor live
        bar, or while the subscription's last entry is still in flight, is skipped; the
        strategy still sees the bar, and exits (paper SL/TP) run in the broker's own
        handler. A venue (async-fill) entry runs as a task so one slow venue call never
        holds the bar; a paper entry fills inline.
        """
        published_at = get_current_time()
        self._running_bar_handlers += 1
        try:
            for strategy in self._find_strategies(event.symbol, event.interval):
                assert event.bar_start is not None
                last = self._last_bar_start.get(strategy.id)
                if last is not None and event.bar_start <= last:
                    continue
                # Recorded before the next await, so a second publish of this bar is ignored.
                self._last_bar_start[strategy.id] = event.bar_start
                successor = True
                if event.bar_end is not None and last is not None:
                    calendar = await self._calendar_factory.for_symbol(event.symbol)
                    step = timedelta(seconds=INTERVAL_SECONDS[event.interval])
                    successor = not calendar.trading_minutes(last + step, event.bar_start)

                bar = {
                    "symbol": event.symbol,
                    "interval": event.interval,
                    "open": event.open,
                    "high": event.high,
                    "low": event.low,
                    "close": event.close,
                    "volume": event.volume,
                    "timestamp": event.bar_start,
                }
                try:
                    signal = await strategy.on_bar_completed(bar)
                except Exception as e:
                    logger.error("strategy_on_bar_error", strategy_id=strategy.id, error=str(e))
                    continue
                if not signal:
                    continue

                signal_at = get_current_time()
                reason = None
                age_s = None
                if event.bar_end is not None:
                    age_s = (signal_at - event.bar_end).total_seconds()
                    if age_s > _STALE_AFTER_S[event.interval]:
                        reason = "stale"
                    elif event.gap or not successor:
                        reason = "gap"
                running = self._signal_tasks.get(strategy.id)
                if reason is None and running is not None and not running.done():
                    reason = "inflight"
                if reason is not None:
                    logger.warning(
                        "strategy.entry_skipped",
                        reason=reason,
                        subscription_id=strategy.id,
                        symbol=event.symbol,
                        interval=event.interval,
                        bar_start=event.bar_start.isoformat(),
                        age_s=None if age_s is None else round(age_s, 1),
                    )
                    await self._notify_rejected(strategy, reason)
                    continue
                broker = self._brokers.get(strategy.id)
                if broker is None or not broker.fills_async:
                    await self._process_signal(strategy, signal, event, signal_at, published_at)
                    continue
                task = asyncio.create_task(
                    self._process_signal(strategy, signal, event, signal_at, published_at)
                )
                self._signal_tasks[strategy.id] = task
                task.add_done_callback(partial(self._forget_signal_task, strategy.id))
        finally:
            self._running_bar_handlers -= 1

    def _forget_signal_task(self, strategy_id: str, task: asyncio.Task[None]) -> None:
        # A later task of the same subscription may already hold the slot.
        if self._signal_tasks.get(strategy_id) is task:
            del self._signal_tasks[strategy_id]

    def inflight_count(self) -> int:
        """Venue signal tasks and bar handlers still running plus orders the brokers have
        not settled; the trader hands over at 0."""
        return (
            sum(not t.done() for t in self._signal_tasks.values())
            + self._running_bar_handlers
            + sum(b.inflight_count for b in set(self._brokers.values()))
        )

    def cancel_pending_signals(self) -> int:
        """A lost lease calls this: tasks that have not reached the broker stop now; a task
        at the broker is stopped by the order deadline check there."""
        self._discard_reason = "lease"
        cancelled = 0
        for strategy_id, task in self._signal_tasks.items():
            if task.done() or strategy_id in self._sending:
                continue
            task.cancel()
            logger.info("strategy.signal_discarded", reason="lease", subscription_id=strategy_id)
            cancelled += 1
        return cancelled

    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        """Route a fill to its owning strategy by subscription_id.

        ``event.subscription_id`` equals the strategy's registration key
        (Signal.subscription_id = strategy.id propagates through Order →
        OrderFilledEvent). The strategy uses the fill's ``side`` to reset its
        open-direction on a round-trip close. Entry, synthetic SL/TP exit, and
        live broker fills all flow through this one handler.
        """
        strategy = self._strategies.get(event.subscription_id)
        if strategy is None or not strategy.is_running:
            return
        try:
            await strategy.on_order_filled(event, event.filled_price)
        except Exception as e:
            logger.error(
                "strategy_on_order_filled_error",
                strategy_id=event.subscription_id,
                error=str(e),
            )

    async def _on_order_cancelled(self, event: OrderCancelledEvent) -> None:
        """Tell the owning strategy that a broker cancelled its submitted order."""
        strategy = self._strategies.get(event.subscription_id)
        if strategy is None or not strategy.is_running:
            return
        await self._notify_rejected(strategy, event.reason)

    async def _notify_rejected(self, strategy: IStrategyService, reason: str) -> None:
        try:
            await strategy.on_order_rejected(reason)
        except Exception as e:
            logger.error(
                "strategy_on_order_rejected_error",
                strategy_id=strategy.id,
                error=str(e),
            )

    def _find_strategies(self, symbol: str, interval: str) -> list[IStrategyService]:
        """Find running strategies on this composite symbol and interval."""
        matches = []
        for strategy in self._strategies.values():
            if not strategy.is_running:
                continue
            if strategy.config.symbol != symbol:
                continue
            if strategy.config.interval != interval:
                continue
            matches.append(strategy)
        return matches

    async def _process_signal(
        self,
        strategy: IStrategyService,
        signal: Signal,
        event: BarCompletedEvent,
        signal_at: datetime,
        published_at: datetime,
    ) -> None:
        """Size and send one entry; no entry leaves while ``trading_until`` is None or past."""
        try:
            if self.trading_until is None:
                reason = self._discard_reason
                # standby discards every bar of a warm standby trader; drain and lease
                # only happen around a handover.
                log = logger.debug if reason == "standby" else logger.info
                log("strategy.signal_discarded", reason=reason, subscription_id=strategy.id)
                await strategy.on_order_rejected(reason)
                return
            deadline = self.trading_until
            if get_current_time() >= deadline:
                logger.warning(
                    "strategy.entry_skipped",
                    reason="lease",
                    subscription_id=strategy.id,
                    symbol=event.symbol,
                    interval=event.interval,
                    bar_start=event.bar_start.isoformat() if event.bar_start else None,
                    age_s=None,
                )
                await strategy.on_order_rejected("lease")
                return

            broker = self._brokers.get(strategy.id)
            if not broker:
                logger.warning("no_broker_for_strategy", strategy_id=strategy.id)
                await strategy.on_order_rejected("no broker")
                return

            current_price = event.close
            balance = await broker.get_balance()

            position = self._position_app_service.get(strategy.id)

            valid, reason = self._risk_check_handler.validate(
                signal,
                balance,
                position,
                strategy.config.risk,
            )
            if not valid:
                logger.info(
                    "signal_rejected_by_risk",
                    strategy_id=strategy.id,
                    reason=reason,
                )
                await strategy.on_order_rejected(reason)
                return

            stop_loss = signal.stop_loss_price or (
                current_price * (1 - _FALLBACK_SL_PCT)
                if signal.direction == Direction.LONG
                else current_price * (1 + _FALLBACK_SL_PCT)
            )

            calc = PositionCalculatorDomainService.calculate(
                balance.available_balance,
                current_price,
                stop_loss,
                strategy.config.risk,
                contract_spec=strategy.config.contract_spec,
            )
            size = calc.size

            if size <= 0:
                logger.info("zero_position_size", strategy_id=strategy.id)
                await strategy.on_order_rejected("zero position size")
                return

            normalized = await broker.normalize_quantity(signal.symbol, size)
            if normalized is None:
                logger.info("order_quantity_below_broker_minimum", strategy_id=strategy.id)
                await strategy.on_order_rejected("quantity below broker minimum")
                return
            size = normalized

            order = self._create_order(strategy, signal, size, current_price)

            self._sending.add(strategy.id)
            try:
                t5 = get_current_time()
                result = await self._order_app_service.submit(order, broker, deadline=deadline)
                t6 = get_current_time()
            finally:
                self._sending.discard(strategy.id)
            if not result.is_success:
                await strategy.on_order_rejected(result.error_message or "rejected")

            logger.debug(
                "signal_processed",
                strategy_id=strategy.id,
                direction=signal.direction.value,
                size=size,
                order_status=result.status.value,
            )
            if event.bar_end is not None:
                # One line per live signal: bounded, so INFO.
                logger.info(
                    "live.signal_latency",
                    subscription_id=strategy.id,
                    symbol=event.symbol,
                    interval=event.interval,
                    bar_start=event.bar_start.isoformat() if event.bar_start else None,
                    closed_by=event.closed_by,
                    t0_bar_end=event.bar_end.isoformat(),
                    t1_closing_tick=(
                        event.closing_tick_at.isoformat() if event.closing_tick_at else None
                    ),
                    t2_closed=event.closed_at.isoformat() if event.closed_at else None,
                    t3_published=published_at.isoformat(),
                    t4_signal=signal_at.isoformat(),
                    t5_submit=t5.isoformat(),
                    t6_returned=t6.isoformat(),
                    t0_t5_ms=int((t5 - event.bar_end).total_seconds() * 1000),
                    t0_t6_ms=int((t6 - event.bar_end).total_seconds() * 1000),
                )
        except Exception as e:
            logger.error("strategy_on_bar_error", strategy_id=strategy.id, error=str(e))
            await self._notify_rejected(strategy, str(e))

    def _create_order(
        self,
        strategy: IStrategyService,
        signal: Signal,
        size: float,
        current_price: float,
    ) -> OrderAggregate:
        side = OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL

        return OrderAggregate.create(
            subscription_id=strategy.id,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=size,
            price=current_price,
            sl_price=signal.stop_loss_price,
            tp_price=signal.take_profit_price,
        )

    async def _forward_trade_to_bus(self, event: TradeClosedEvent) -> None:
        """Republish a broker trade-closure onto the bus for the live collector.

        Backtest bypasses this — it wires the collector directly onto its own
        broker via ``inject_prepared_strategy`` — so the two trade channels never
        cross and a backtest trade is never double-counted.
        """
        await self._event_bus.publish(event)

    async def _get_or_create_broker(
        self, broker_type: str, contract_spec: ContractSpec
    ) -> IBrokerPort:
        key = (broker_type, contract_spec if broker_type == "paper" else None)
        broker = self._broker_pool.get(key)
        # Only paper prices fills by contract spec and retires with its last holder.
        # A venue broker is one account, so one instance and one event stream per process.
        if broker is not None and (
            broker_type != "paper" or any(b is broker for b in self._brokers.values())
        ):
            return broker

        config = {**self._default_broker_config, "contract_spec": contract_spec}
        broker = self._broker_factory.create(broker_type, config)
        # Live path only (reached via load_strategy). Wire once, on creation — the
        # pool hit above returns already-wired brokers, so N subscriptions
        # sharing one broker get exactly one forward, not one per subscription.
        await broker.subscribe_trades(self._forward_trade_to_bus)
        if broker.fills_async:
            await broker.subscribe_order_updates(self._order_app_service.on_order_update)
        self._broker_pool[key] = broker
        return broker


class _DefaultStrategy(IStrategyService):
    """Default pass-through strategy that never generates signals."""

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return None
