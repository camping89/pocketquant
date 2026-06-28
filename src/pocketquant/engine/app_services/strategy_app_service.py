import asyncio
from typing import TYPE_CHECKING

import structlog

from pocketquant.core.common.messaging import (
    EventBus,
    EventRegistry,
    event_handler,
    get_event_registry,
)
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.interfaces import IBroker, IBrokerFactory
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderType,
)
from pocketquant.core.domain.quote.events import QuoteReceivedEvent
from pocketquant.core.domain.risk import PositionSizer
from pocketquant.core.domain.strategy.interfaces import IStrategy
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig

if TYPE_CHECKING:
    from pocketquant.engine.app_services.order_app_service import OrderAppService
    from pocketquant.engine.app_services.position_app_service import PositionAppService
    from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler

logger = structlog.get_logger(__name__)


class StrategyAppService:
    """Engine for managing and executing trading strategies.

    Subscribes to market events and dispatches to registered strategies.
    Coordinates signal processing through risk checks and order submission.
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker_factory: IBrokerFactory,
        order_app_service: OrderAppService,
        position_app_service: PositionAppService,
        risk_check_handler: RiskCheckHandler,
        default_broker_config: dict | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._broker_factory = broker_factory
        self._order_app_service = order_app_service
        self._position_app_service = position_app_service
        self._risk_check_handler = risk_check_handler
        self._default_broker_config = default_broker_config or {}

        self._strategies: dict[str, IStrategy] = {}
        self._brokers: dict[str, IBroker] = {}
        self._configs: dict[str, StrategyConfig] = {}
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, registry: EventRegistry | None = None) -> None:
        """Subscribe handlers to the event bus and mark running.

        Per-run backtest engines pass a local ``registry`` so their handler
        bindings don't accumulate in the process-global registry across many
        runs; the local registry (and the per-run bus it bound to) is discarded
        when the run ends. The live engine passes nothing → global registry.
        """
        if self._running:
            return

        registry = registry or get_event_registry()
        registry.register_instance(self, self._event_bus)
        self._running = True

        logger.info("strategy_engine_started")

    async def stop(self) -> None:
        if not self._running:
            return

        for strategy_id in list(self._strategies.keys()):
            await self.stop_strategy(strategy_id)

        for broker in self._brokers.values():
            await broker.disconnect()

        self._running = False
        logger.info("strategy_engine_stopped")

    async def load_strategy(
        self,
        config: StrategyConfig,
        strategy_class: type[IStrategy] | None = None,
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

            broker = await self._get_or_create_broker(config.broker)

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
        async with self._lock:
            if strategy_id not in self._strategies:
                raise ValueError(f"Strategy not found: {strategy_id}")

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                return

            broker = self._brokers[strategy_id]
            if not broker.is_connected:
                await broker.connect()

            await strategy.on_start()

            logger.info("strategy_started", strategy_id=strategy_id)

    async def stop_strategy(self, strategy_id: str) -> None:
        async with self._lock:
            if strategy_id not in self._strategies:
                return

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                await strategy.on_stop()

            logger.info("strategy_stopped", strategy_id=strategy_id)

    async def unload_strategy(self, strategy_id: str) -> None:
        await self.stop_strategy(strategy_id)

        async with self._lock:
            self._strategies.pop(strategy_id, None)
            self._brokers.pop(strategy_id, None)
            self._configs.pop(strategy_id, None)

            logger.info("strategy_unloaded", strategy_id=strategy_id)

    async def inject_prepared_strategy(
        self,
        sid: str,
        strategy: IStrategy,
        broker: IBroker,
        config: StrategyConfig,
    ) -> None:
        """Register an externally-prepared strategy+broker pair under ``sid``.

        Backtest callers build their own PaperBroker and strategy instance (to
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

    def get_strategies(self) -> list[dict]:
        return [
            {
                "id": s.id,
                "name": s.config.name,
                "symbol": s.config.symbol,
                "interval": s.config.interval,
                "broker": s.config.broker,
                "is_running": s.is_running,
            }
            for s in self._strategies.values()
        ]

    def get_strategy(self, strategy_id: str) -> IStrategy | None:
        return self._strategies.get(strategy_id)

    def loaded_strategy_ids(self) -> list[str]:
        """Return all currently-loaded instance keys (snapshot, lock-free read).

        Keys are either subscription ids (uuid7 strings) or synthetic
        backtest ids (``{code}::bt::{sub_id}``). The reconcile orphan-unload pass
        filters on shape so it never touches synthetic backtest instances.
        """
        return list(self._strategies.keys())

    @event_handler(BarCompletedEvent)
    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        strategies = self._find_strategies(event.symbol, event.interval, trigger="bar")

        for strategy in strategies:
            try:
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

                signal = await strategy.on_bar_completed(bar)

                if signal:
                    await self._process_signal(strategy, signal, event.close)

            except Exception as e:
                logger.error(
                    "strategy_on_bar_error",
                    strategy_id=strategy.id,
                    error=str(e),
                )

    @event_handler(QuoteReceivedEvent)
    async def _on_quote_received(self, event: QuoteReceivedEvent) -> None:
        strategies = self._find_strategies(event.symbol, trigger="tick")

        for strategy in strategies:
            try:
                tick = {
                    "symbol": event.symbol,
                    "price": event.price,
                    "volume": event.volume,
                    "timestamp": event.timestamp,
                }

                order = await strategy.on_quote_received(tick)

                if order:
                    broker = self._brokers.get(strategy.id)
                    if broker:
                        await self._order_app_service.submit(order, broker)

            except Exception as e:
                logger.error(
                    "strategy_on_tick_error",
                    strategy_id=strategy.id,
                    error=str(e),
                )

    @event_handler(OrderFilledEvent)
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

    def _find_strategies(
        self,
        symbol: str,
        interval: str | None = None,
        trigger: str = "bar",
    ) -> list[IStrategy]:
        """Find strategies matching composite symbol/interval/trigger."""
        matches = []
        for strategy in self._strategies.values():
            if not strategy.is_running:
                continue
            if strategy.config.symbol != symbol:
                continue
            if interval and strategy.config.interval != interval:
                continue
            if strategy.config.trigger != trigger:
                continue
            matches.append(strategy)
        return matches

    async def _process_signal(
        self, strategy: IStrategy, signal: Signal, current_price: float
    ) -> None:
        broker = self._brokers.get(strategy.id)
        if not broker:
            logger.warning("no_broker_for_strategy", strategy_id=strategy.id)
            return

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
            return

        stop_loss = signal.stop_loss_price or (
            current_price * (1 - strategy.config.orders.stop_loss.distance_percent)
            if signal.direction == Direction.LONG
            else current_price * (1 + strategy.config.orders.stop_loss.distance_percent)
        )

        size = PositionSizer.calculate_size(
            balance.available_balance,
            current_price,
            stop_loss,
            strategy.config.risk,
        )

        if size <= 0:
            logger.info("zero_position_size", strategy_id=strategy.id)
            return

        order = self._create_order(strategy, signal, size, current_price)

        result = await self._order_app_service.submit(order, broker)

        logger.info(
            "signal_processed",
            strategy_id=strategy.id,
            direction=signal.direction.value,
            size=size,
            order_status=result.status.value,
        )

    def _create_order(
        self,
        strategy: IStrategy,
        signal: Signal,
        size: float,
        current_price: float,
    ) -> OrderAggregate:
        side = OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL

        order_type = (
            OrderType.MARKET if strategy.config.orders.entry_type == "market" else OrderType.LIMIT
        )

        price = signal.entry_price if order_type == OrderType.LIMIT else current_price

        return OrderAggregate.create(
            subscription_id=strategy.id,
            symbol=signal.symbol,
            side=side,
            order_type=order_type,
            quantity=size,
            price=price,
            sl_price=signal.stop_loss_price,
            tp_price=signal.take_profit_price,
        )

    async def _get_or_create_broker(self, broker_type: str) -> IBroker:
        for broker in self._brokers.values():
            if broker.name == broker_type or broker.name == f"{broker_type}-demo":
                return broker

        config = self._default_broker_config.copy()
        broker = self._broker_factory.create(broker_type, config)
        return broker


class _DefaultStrategy(IStrategy):
    """Default pass-through strategy that never generates signals."""

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return None
