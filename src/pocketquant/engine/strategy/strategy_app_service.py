import asyncio
from bisect import bisect_right
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING

import structlog

from pocketquant.core.common.constants import (
    CACHE_KEY_STRATEGY_SNAPSHOT,
    INTERVAL_SECONDS,
    TTL_STRATEGY_SNAPSHOT,
)
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.broker_factory_port import IBrokerFactoryPort
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.brokers.events import REASON_MANUAL_CLOSE, REASON_STRATEGY_EXIT
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate, PositionSide, TradeClosedEvent
from pocketquant.core.domain.risk import PositionCalculatorDomainService
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from pocketquant.core.domain.subscription import ManualAction
from pocketquant.core.domain.symbol import ContractSpec
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

if TYPE_CHECKING:
    from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
    from pocketquant.core.infra.persistence.redis import Cache
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
# sync_1m settles the last bucket of every cascaded interval at second 12; a start with stored
# entry bars before second 20 waits for it.
_WARMUP_READY_SECOND = 20
# Snapshot records kept per subscription.
_SNAPSHOT_RING = 20


def _direction_of(position: PositionAggregate | None) -> Direction | None:
    if position is None:
        return None
    return Direction.LONG if position.side == PositionSide.LONG else Direction.SHORT


def closed_before(bars: list[Bar], step: timedelta, instant: datetime) -> list[Bar]:
    return [b for b in bars if b.datetime is not None and b.datetime + step <= instant]


def _bar_dict(symbol: str, interval: str, source: Bar | BarCompletedEvent, start: datetime) -> dict:
    return {
        "symbol": symbol,
        "interval": interval,
        "open": source.open,
        "high": source.high,
        "low": source.low,
        "close": source.close,
        "volume": source.volume,
        "timestamp": start,
    }


# What the strategy reported for the bar, with what the engine did about it.
def _bar_record(
    strategy: IStrategyService, bar_start: datetime, interval: str | None, outcome: str
) -> dict:
    snapshot = strategy.snapshot or {}
    return {
        "bar_start": bar_start.isoformat(),
        "interval": interval,
        "readings": snapshot.get("readings", []),
        "decision": snapshot.get("decision"),
        "outcome": outcome,
    }


class StrategyAppService:
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
        cache: Cache | None = None,
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
        self._cache = cache

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
        self._signal_tasks: dict[str, asyncio.Task[str]] = {}
        self._last_bar_start: dict[str, datetime] = {}
        # _on_bar_completed calls still running, inline paper fills included; the trader
        # hands over at 0.
        self._running_bar_handlers = 0
        # Subscriptions whose signal reached the broker call; a lost lease never cancels those.
        self._sending: set[str] = set()
        # Why a None switch discards: standby before take_over(), drain after it, lease
        # after cancel_pending_signals().
        self._discard_reason = "standby"
        # Process lifetime in live, one run in a backtest; one entry per (symbol, higher interval).
        self._context: dict[tuple[str, str], tuple[datetime, list[Bar], bool]] = {}
        # A backtest's higher bars for the whole run, oldest first, with their starts.
        self._preloaded: dict[tuple[str, str], tuple[list[datetime], list[Bar]]] = {}
        # The last decided bars per subscription, oldest first; the lease holder mirrors
        # them to Redis for the UI.
        self._snapshots: dict[str, deque[dict]] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    # A broker subscribes to BarCompletedEvent when it connects, which is after this,
    # so strategies see a bar before the broker checks SL/TP.
    async def start(self) -> None:
        if self._running:
            return

        self._event_bus.subscribe(BarCompletedEvent, self._on_bar_completed)
        self._event_bus.subscribe(OrderCancelledEvent, self._on_order_cancelled)
        self._event_bus.subscribe(OrderFilledEvent, self._on_order_filled)
        self._running = True

        logger.info("strategy_engine_started")

    # timeout_s is what is left of the caller's shutdown grace.
    async def stop(self, timeout_s: float) -> None:
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

    # Runs once per process, before bars flow.
    async def take_over(self) -> None:
        async with self._lock:
            await self._order_app_service.load_pending_orders()
            await self._position_app_service.load_open_positions()
            restored = 0
            papers = {id(b): b for b in self._brokers.values() if isinstance(b, PaperBrokerAdapter)}
            for broker in papers.values():
                ids = [sid for sid, b in self._brokers.items() if b is broker]
                rows = []
                for sid in ids:
                    row = self._position_app_service.get(sid)
                    if row is None:
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
            # A stored stop belongs to the previous trader: the strategy re-places it.
            stops_dropped = 0
            for sid in self._strategies:
                order = self._order_app_service.pending_stop(sid)
                if order is None:
                    continue
                bound = self._brokers.get(sid)
                broker_cancelled = bound is not None and await bound.cancel_order(
                    order.broker_order_id or ""
                )
                await self._order_app_service.cancel(order)
                logger.info(
                    "strategy.pending_stop_dropped",
                    subscription_id=sid,
                    order_id=str(order.id),
                    broker_cancelled=broker_cancelled,
                )
                stops_dropped += 1
            # From now on a None switch means a drain, unless a lost lease marks it.
            self._discard_reason = "drain"
            logger.info(
                "strategy_engine.took_over",
                strategies=len(self._strategies),
                paper_brokers=len(papers),
                paper_positions=restored,
                paper_stops_dropped=stops_dropped,
            )

    async def load_strategy(
        self,
        config: StrategyConfig,
        strategy_class: type[IStrategyService] | None = None,
    ) -> str:
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

    # Warm-up replays up to 500 stored bars; their signals are rejected, never sent.
    # A standby engine does not connect the broker.
    async def start_strategy(self, strategy_id: str) -> None:
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
            interval = Interval(config.intervals[0])
            step = timedelta(seconds=INTERVAL_SECONDS[config.intervals[0]])
            calendar = await self._calendar_factory.for_symbol(config.symbol)
            bars = await self._closed_bars(config.symbol, interval, step, now)
            last = bars[-1].datetime if bars else None
            # A cascaded interval stores its in-progress bar, so before sync_1m settles the
            # last bucket at second 12 the newest stored entry and higher bars may be
            # partial; wait for it.
            if now.second < _WARMUP_READY_SECOND and bars:
                await asyncio.sleep(_WARMUP_READY_SECOND - now.second - now.microsecond / 1e6)
                now = get_current_time()
                bars = await self._closed_bars(config.symbol, interval, step, now)
                last = bars[-1].datetime if bars else None

            await self._refresh_context(config, now)

            # No I/O from here to the direction restore.
            await strategy.on_start()
            for stored in bars:
                assert stored.datetime is not None
                signal = await self._decide(
                    strategy, _bar_dict(config.symbol, config.intervals[0], stored, stored.datetime)
                )
                if signal:
                    await strategy.on_order_rejected("warmup")
                outcome = "skipped:warmup" if signal else "no_signal"
                await self._record_snapshot(
                    strategy_id,
                    _bar_record(strategy, stored.datetime, config.intervals[0], outcome),
                    write=False,
                )
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
        found = await self._bar_repository.find(symbol, interval, end_date=now, limit=_WARMUP_BARS)
        return closed_before(list(reversed(found)), step, now)

    # A backtest replays thousands of rollovers, and one Mongo round trip per rollover costs
    # more than the whole replay of a bar, so a run reads each higher interval once.
    async def preload_context(self, config: StrategyConfig, start: datetime, end: datetime) -> None:
        for name in config.intervals[1:]:
            step = timedelta(seconds=INTERVAL_SECONDS[name])
            # Newest first: every bar the run can reach plus the warm-up window before it.
            limit = max(0, int((end - start) / step)) + 1 + _WARMUP_BARS
            found = await self._bar_repository.find(
                config.symbol, Interval(name), end_date=end, limit=limit
            )
            bars = [b for b in reversed(found) if b.datetime is not None]
            self._preloaded[(config.symbol, name)] = ([b.datetime for b in bars], bars)  # type: ignore[misc]

    # A window is re-read until its previous bucket is stored or has no trading minutes.
    async def _refresh_context(self, config: StrategyConfig, instant: datetime) -> None:
        if len(config.intervals) < 2:
            return
        for name in config.intervals[1:]:
            step = timedelta(seconds=INTERVAL_SECONDS[name])
            cached = self._context.get((config.symbol, name))
            # Every calendar bucket is exactly one step long, so an instant inside a complete
            # cached window needs no calendar call; a backtest runs this on every replayed bar.
            if cached is not None and cached[2] and cached[0] <= instant < cached[0] + step:
                continue
            interval = Interval(name)
            calendar = await self._calendar_factory.for_symbol(config.symbol)
            window = calendar.bar_start(instant, interval)
            preloaded = self._preloaded.get((config.symbol, name))
            if preloaded is None:
                bars = await self._closed_bars(config.symbol, interval, step, instant)
            else:
                # The same slice _closed_bars reads: the newest bars that start by the instant.
                starts, stored = preloaded
                end = bisect_right(starts, instant)
                bars = closed_before(stored[max(0, end - _WARMUP_BARS) : end], step, instant)
            complete = (bool(bars) and bars[-1].datetime == window - step) or not (
                calendar.trading_minutes(window - step, window)
            )
            logger.debug(
                "strategy.context_loaded",
                symbol=config.symbol,
                interval=name,
                window=window.isoformat(),
                bars=len(bars),
            )
            if not complete and (cached is None or cached[0] != window):
                logger.warning(
                    "strategy.context_previous_bucket_missing",
                    symbol=config.symbol,
                    interval=name,
                    window=window.isoformat(),
                )
            self._context[(config.symbol, name)] = (window, bars, complete)

    # The instant is the entry bar's start, so an entry bar never reads its own higher
    # bucket (docs/governance/no-look-ahead-rules.md).
    def _context_at(self, config: StrategyConfig, instant: datetime) -> dict[str, list[Bar]]:
        out = {}
        for n in config.intervals[1:]:
            cached = self._context[(config.symbol, n)][1]
            step = timedelta(seconds=INTERVAL_SECONDS[n])
            # Cached bars are oldest first, so when the newest is closed at the instant all are
            # (live and backtest); warm-up replays earlier instants and filters.
            if closed_before(cached[-1:], step, instant):
                # Strategies must never mutate a context list, because it is the shared cache.
                out[n] = cached
            else:
                out[n] = closed_before(cached, step, instant)
        return out

    async def _decide(self, strategy: IStrategyService, bar: dict) -> Signal | None:
        strategy.snapshot = None
        bar["context"] = self._context_at(strategy.config, bar["timestamp"])
        return await strategy.on_bar_completed(bar)

    async def stop_strategy(self, strategy_id: str) -> None:
        async with self._lock:
            if strategy_id not in self._strategies:
                return

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                await strategy.on_stop()

            # A resting stop never outlives its strategy: stop, unload, edit and handover all
            # cancel it, and the strategy re-places it on its next bar.
            pending = self._order_app_service.pending_stop(strategy_id)
            broker = self._brokers.get(strategy_id)
            if pending is not None and broker is not None:
                await self._cancel_stop(pending, broker)

            logger.info("strategy_stopped", strategy_id=strategy_id)

    async def _cancel_stop(self, order: OrderAggregate, broker: IBrokerPort) -> bool:
        if await broker.cancel_order(order.broker_order_id or ""):
            await self._order_app_service.cancel(order)
            return True
        logger.warning(
            "strategy.pending_cancel_failed",
            subscription_id=order.subscription_id,
            order_id=str(order.id),
        )
        return False

    # None leaves the action queued for the next reconcile tick. Any other return is an
    # attempt through the paths a strategy uses, and the caller clears the action with it.
    async def manual_action(self, subscription_id: str, action: ManualAction) -> str | None:
        if self.trading_until is None:
            return None
        broker = self._brokers.get(subscription_id)
        if broker is None:
            outcome = "rejected:no_broker"
        elif isinstance(broker, PaperBrokerAdapter) and not broker.has_price(
            self._configs[subscription_id].symbol
        ):
            # Right after a takeover the paper broker has no price, and a close would fill
            # at the stored entry price.
            logger.debug("manual_action.waiting_for_price", subscription_id=subscription_id)
            return None
        else:
            pending = self._order_app_service.pending_stop(subscription_id)
            # A close goes even when the cancel fails.
            cancelled = pending is not None and await self._cancel_stop(pending, broker)
            position = self._position_app_service.get(subscription_id)
            if action == "close" and position is not None:
                closed = await broker.close_position(
                    subscription_id,
                    position.symbol,
                    reason=REASON_MANUAL_CLOSE,
                    deadline=self.trading_until,
                )
                outcome = "accepted" if closed else "rejected:close_failed"
            elif pending is None:
                outcome = (
                    "rejected:nothing_pending" if action == "cancel" else "rejected:nothing_open"
                )
            else:
                outcome = "accepted" if cancelled else "rejected:cancel_failed"
        record = {
            "bar_start": get_current_time().isoformat(),
            "interval": None,
            "readings": [],
            "decision": {"action": f"manual_{action}", "reason": "owner request"},
            "outcome": outcome,
        }
        await self._record_snapshot(subscription_id, record, write=True)
        logger.info(
            "manual_action.done", subscription_id=subscription_id, action=action, outcome=outcome
        )
        return outcome

    # A paper broker simulates the position, so the subscription's position is dropped
    # and a broker with no other holder is disconnected; otherwise it keeps checking
    # SL/TP for no one. A venue keeps its position under its own SL/TP, so that one is
    # only logged.
    async def unload_strategy(self, strategy_id: str) -> None:
        await self.stop_strategy(strategy_id)

        async with self._lock:
            self._strategies.pop(strategy_id, None)
            broker = self._brokers.pop(strategy_id, None)
            self._configs.pop(strategy_id, None)
            self._last_bar_start.pop(strategy_id, None)
            self._snapshots.pop(strategy_id, None)

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

    # Registration, broker connection and on_start() must share one critical section:
    # start_strategy also takes _lock, so a split would race unload_strategy and could
    # leave a strategy never started or a broker never connected (silent zero-trade
    # backtests).
    async def inject_prepared_strategy(
        self,
        sid: str,
        strategy: IStrategyService,
        broker: IBrokerPort,
        config: StrategyConfig,
    ) -> None:
        async with self._lock:
            if not any(b is broker for b in self._brokers.values()):
                await broker.subscribe_order_updates(self._order_app_service.on_order_update)
            self._strategies[sid] = strategy
            self._brokers[sid] = broker
            self._configs[sid] = config
            if not broker.is_connected:
                await broker.connect()
            await strategy.on_start()

    def get_config(self, sid: str) -> StrategyConfig | None:
        return self._configs.get(sid)

    def get_strategy(self, strategy_id: str) -> IStrategyService | None:
        return self._strategies.get(strategy_id)

    # Keys are subscription ids in the live engine and strategy codes in a backtest
    # sandbox; an engine only ever holds one kind.
    def loaded_strategy_ids(self) -> list[str]:
        return list(self._strategies.keys())

    # An entry on a stale, gapped or non-successor live bar, or while the last entry is
    # still in flight, is skipped; the strategy still sees the bar. An exit is never stale:
    # going flat is not a look-ahead risk. An exit behind an in-flight entry is skipped as
    # inflight, and the strategy sends it again on its next bar. A venue entry runs as a
    # task so one slow venue call never holds the bar; a paper entry fills inline.
    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        published_at = get_current_time()
        self._running_bar_handlers += 1
        try:
            # Stops resting from earlier bars fill, and SL/TP exits run, before any strategy
            # decides on this bar. A fill is an entry, so it needs the lease like any other.
            if self.trading_until is not None and published_at < self.trading_until:
                running = {sid for sid, s in self._strategies.items() if s.is_running}
                papers = {
                    id(b): b
                    for b in self._brokers.values()
                    if isinstance(b, PaperBrokerAdapter) and b.is_connected
                }
                for paper in papers.values():
                    try:
                        await paper.fill_resting_stops(event, running)
                    except Exception:
                        logger.error("paper.stop_fill_failed", symbol=event.symbol, exc_info=True)
            for strategy in self._find_strategies(event.symbol, event.interval):
                outcome = await self._handle_bar(strategy, event, published_at)
                if outcome is None:
                    continue
                assert event.bar_start is not None
                await self._record_snapshot(
                    strategy.id,
                    _bar_record(strategy, event.bar_start, event.interval, outcome),
                    write=event.bar_end is not None,
                )
        finally:
            self._running_bar_handlers -= 1

    # The outcome of the bar for the snapshot: no_signal, sent (a venue task counts once
    # spawned), skipped:<reason> or rejected:<reason>; None for a bar already seen.
    async def _handle_bar(
        self, strategy: IStrategyService, event: BarCompletedEvent, published_at: datetime
    ) -> str | None:
        assert event.bar_start is not None
        last = self._last_bar_start.get(strategy.id)
        if last is not None and event.bar_start <= last:
            return None
        # Recorded before the next await, so a second publish of this bar is ignored.
        self._last_bar_start[strategy.id] = event.bar_start
        successor = True
        if event.bar_end is not None and last is not None:
            calendar = await self._calendar_factory.for_symbol(event.symbol)
            step = timedelta(seconds=INTERVAL_SECONDS[event.interval])
            successor = not calendar.trading_minutes(last + step, event.bar_start)

        try:
            await self._refresh_context(strategy.config, event.bar_start)
            signal = await self._decide(
                strategy, _bar_dict(event.symbol, event.interval, event, event.bar_start)
            )
        except Exception as e:
            logger.error("strategy_on_bar_error", strategy_id=strategy.id, error=str(e))
            return "skipped:strategy_error"
        if not signal:
            return "no_signal"

        signal_at = get_current_time()
        reason = None
        age_s = None
        if event.bar_end is not None and signal.direction is not Direction.EXIT:
            age_s = (signal_at - event.bar_end).total_seconds()
            if age_s > _STALE_AFTER_S[event.interval]:
                reason = "stale"
            elif event.gap or not successor:
                reason = "gap"
        inflight = self._signal_tasks.get(strategy.id)
        if reason is None and inflight is not None and not inflight.done():
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
            return f"skipped:{reason}"
        broker = self._brokers.get(strategy.id)
        if broker is None or not broker.fills_async:
            return await self._process_signal(strategy, signal, event, signal_at, published_at)
        task = asyncio.create_task(
            self._process_signal(strategy, signal, event, signal_at, published_at)
        )
        self._signal_tasks[strategy.id] = task
        task.add_done_callback(partial(self._forget_signal_task, strategy.id))
        return "sent"

    # The ring stays in memory for every bar; only live bars reach Redis, and only while
    # this engine holds the lease. A failed write never blocks trading.
    async def _record_snapshot(self, sid: str, record: dict, *, write: bool) -> None:
        pending = self._order_app_service.pending_stop(sid)
        record["pending"] = (
            None if pending is None else {"side": pending.side.value, "price": pending.stop_price}
        )
        ring = self._snapshots.setdefault(sid, deque(maxlen=_SNAPSHOT_RING))
        ring.append(record)
        if not write or self._cache is None or self.trading_until is None:
            return
        try:
            await self._cache.set(
                CACHE_KEY_STRATEGY_SNAPSHOT.format(subscription_id=sid),
                list(ring),
                ttl=TTL_STRATEGY_SNAPSHOT,
            )
        except Exception:
            logger.warning("strategy.snapshot_write_failed", subscription_id=sid, exc_info=True)

    def _forget_signal_task(self, strategy_id: str, task: asyncio.Task[str]) -> None:
        # A later task of the same subscription may already hold the slot.
        if self._signal_tasks.get(strategy_id) is task:
            del self._signal_tasks[strategy_id]

    # The trader hands over only at 0.
    def inflight_count(self) -> int:
        return (
            sum(not t.done() for t in self._signal_tasks.values())
            + self._running_bar_handlers
            + sum(b.inflight_count for b in set(self._brokers.values()))
        )

    # Called on a lost lease. A task already at the broker is stopped by the order
    # deadline check there.
    def cancel_pending_signals(self) -> int:
        self._discard_reason = "lease"
        cancelled = 0
        for strategy_id, task in self._signal_tasks.items():
            if task.done() or strategy_id in self._sending:
                continue
            task.cancel()
            logger.info("strategy.signal_discarded", reason="lease", subscription_id=strategy_id)
            cancelled += 1
        return cancelled

    # event.subscription_id equals the strategy's registration key (Signal ->
    # Order -> OrderFilledEvent). Entry, synthetic SL/TP exit and live broker fills
    # all flow through this one handler.
    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
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
        matches = []
        for strategy in self._strategies.values():
            if not strategy.is_running:
                continue
            if strategy.config.symbol != symbol:
                continue
            if strategy.config.intervals[0] != interval:
                continue
            matches.append(strategy)
        return matches

    # No entry leaves while trading_until is None or past.
    async def _process_signal(
        self,
        strategy: IStrategyService,
        signal: Signal,
        event: BarCompletedEvent,
        signal_at: datetime,
        published_at: datetime,
    ) -> str:
        try:
            if self.trading_until is None:
                reason = self._discard_reason
                # standby discards every bar of a warm standby trader; drain and lease
                # only happen around a handover.
                log = logger.debug if reason == "standby" else logger.info
                log("strategy.signal_discarded", reason=reason, subscription_id=strategy.id)
                await strategy.on_order_rejected(reason)
                return f"rejected:{reason}"
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
                return "rejected:lease"

            broker = self._brokers.get(strategy.id)
            if not broker:
                logger.warning("no_broker_for_strategy", strategy_id=strategy.id)
                await strategy.on_order_rejected("no broker")
                return "rejected:no broker"

            pending = self._order_app_service.pending_stop(strategy.id)
            side = OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL
            if (
                pending is not None
                and signal.entry_type == "stop"
                and pending.side == side
                and pending.stop_price == signal.entry_price
                and pending.sl_price == signal.stop_loss_price
                and pending.tp_price == signal.take_profit_price
            ):
                logger.debug(
                    "strategy.stop_kept", subscription_id=strategy.id, order_id=str(pending.id)
                )
                return "skipped:stop_unchanged"
            # An exit goes flat even when the cancel fails.
            cancelled = pending is not None and await self._cancel_stop(pending, broker)
            if pending is not None and not cancelled and signal.direction is not Direction.EXIT:
                await strategy.on_order_rejected("pending cancel failed")
                return "rejected:pending cancel failed"

            current_price = signal.entry_price if signal.entry_type == "stop" else event.close
            assert current_price is not None
            balance = await broker.get_balance()

            position = self._position_app_service.get(strategy.id)

            valid, reason = self._risk_check_handler.validate(
                signal,
                balance,
                position,
                strategy.config.risk,
            )
            if signal.direction is Direction.EXIT:
                if not valid:
                    if pending is None:
                        logger.debug(
                            "strategy.exit_ignored", subscription_id=strategy.id, reason=reason
                        )
                        return "skipped:nothing_open"
                    return "sent" if cancelled else "rejected:cancel_failed"
                assert position is not None
                closed = await broker.close_position(
                    strategy.id, position.symbol, reason=REASON_STRATEGY_EXIT, deadline=deadline
                )
                logger.info(
                    "strategy.position_close_sent",
                    subscription_id=strategy.id,
                    reason=REASON_STRATEGY_EXIT,
                    closed=closed,
                )
                return "sent" if closed else "rejected:close_failed"
            if not valid:
                logger.info(
                    "signal_rejected_by_risk",
                    strategy_id=strategy.id,
                    reason=reason,
                )
                await strategy.on_order_rejected(reason)
                return f"rejected:{reason}"

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
                return "rejected:zero position size"

            normalized = await broker.normalize_quantity(signal.symbol, size)
            if normalized is None:
                logger.info("order_quantity_below_broker_minimum", strategy_id=strategy.id)
                await strategy.on_order_rejected("quantity below broker minimum")
                return "rejected:quantity below broker minimum"
            size = normalized

            order = self._create_order(strategy, signal, size, current_price)

            self._sending.add(strategy.id)
            try:
                t5 = get_current_time()
                result = await self._order_app_service.submit(order, broker, deadline=deadline)
                t6 = get_current_time()
            finally:
                self._sending.discard(strategy.id)
            outcome = "sent"
            if not result.is_success:
                outcome = f"rejected:{result.error_message or 'rejected'}"
                await strategy.on_order_rejected(result.error_message or "rejected")
            # A stop or unload that ran while this stop was in flight saw no SUBMITTED order
            # to cancel.
            if (
                order.order_type is OrderType.STOP_MARKET
                and order.status is OrderStatus.SUBMITTED
                and (self._strategies.get(strategy.id) is not strategy or not strategy.is_running)
            ):
                await self._cancel_stop(order, broker)

            logger.debug(
                "signal_processed",
                strategy_id=strategy.id,
                direction=signal.direction.value,
                size=size,
                order_status=result.status.value,
            )
            if event.bar_end is not None:
                # One line per live signal: bounded, so INFO. A stop moved every bar is a
                # per-bar event, so DEBUG.
                log = logger.debug if pending is not None else logger.info
                log(
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
            return outcome
        except Exception as e:
            logger.error("strategy_on_bar_error", strategy_id=strategy.id, error=str(e))
            await self._notify_rejected(strategy, str(e))
            return f"rejected:{e}"

    def _create_order(
        self,
        strategy: IStrategyService,
        signal: Signal,
        size: float,
        current_price: float,
    ) -> OrderAggregate:
        side = OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL
        stop = signal.entry_type == "stop"

        return OrderAggregate.create(
            subscription_id=strategy.id,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.STOP_MARKET if stop else OrderType.MARKET,
            quantity=size,
            price=None if stop else current_price,
            stop_price=signal.entry_price if stop else None,
            sl_price=signal.stop_loss_price,
            tp_price=signal.take_profit_price,
        )

    # Backtests bypass this (their collector is wired to their own broker), so a
    # backtest trade never reaches the live collector and is never double-counted.
    async def _forward_trade_to_bus(self, event: TradeClosedEvent) -> None:
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
        await broker.subscribe_order_updates(self._order_app_service.on_order_update)
        self._broker_pool[key] = broker
        return broker


class _DefaultStrategy(IStrategyService):
    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return None
