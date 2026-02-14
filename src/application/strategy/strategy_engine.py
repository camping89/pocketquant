"""Strategy engine - orchestrates strategy execution and event dispatch."""

import asyncio
from typing import TYPE_CHECKING

import structlog

from src.common.messaging import EventBus, event_handler, get_event_registry
from src.domain.ohlcv.ohlcv_event import BarCompletedEvent
from src.domain.order import OrderAggregate, OrderSide, OrderType
from src.domain.quote.quote_event import QuoteReceivedEvent
from src.domain.risk import PositionSizer
from src.domain.strategy.interfaces import IStrategy
from src.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from src.infrastructure.brokers import BrokerFactory, IBroker

if TYPE_CHECKING:
    from src.application.trading.order_manager import OrderManager
    from src.application.trading.position_tracker import PositionTracker
    from src.features.risk.check_risk.handler import RiskCheckHandler

logger = structlog.get_logger(__name__)


class StrategyEngine:
    """Engine for managing and executing trading strategies.

    Subscribes to market events and dispatches to registered strategies.
    Coordinates signal processing through risk checks and order submission.
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker_factory: BrokerFactory,
        order_manager: OrderManager,
        position_tracker: PositionTracker,
        risk_handler: RiskCheckHandler,
        default_broker_config: dict | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._broker_factory = broker_factory
        self._order_manager = order_manager
        self._position_tracker = position_tracker
        self._risk_handler = risk_handler
        self._default_broker_config = default_broker_config or {}

        self._strategies: dict[str, IStrategy] = {}
        self._brokers: dict[str, IBroker] = {}
        self._configs: dict[str, StrategyConfig] = {}
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._running

    async def start(self) -> None:
        """Start the strategy engine and subscribe to events."""
        if self._running:
            return

        # Auto-register decorated event handlers
        registry = get_event_registry()
        registry.register_instance(self, self._event_bus)
        self._running = True

        logger.info("strategy_engine_started")

    async def stop(self) -> None:
        """Stop the strategy engine and all strategies."""
        if not self._running:
            return

        # Stop all strategies
        for strategy_id in list(self._strategies.keys()):
            await self.stop_strategy(strategy_id)

        # Disconnect all brokers
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

            # Create or get broker for this strategy
            broker = await self._get_or_create_broker(config.broker)

            # Create strategy instance (use base class if none provided)
            if strategy_class:
                strategy = strategy_class(config)
            else:
                # Use a simple pass-through strategy for now
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
        """Start a loaded strategy."""
        async with self._lock:
            if strategy_id not in self._strategies:
                raise ValueError(f"Strategy not found: {strategy_id}")

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                return

            # Connect broker if needed
            broker = self._brokers[strategy_id]
            if not broker.is_connected:
                await broker.connect()

            await strategy.on_start()

            logger.info("strategy_started", strategy_id=strategy_id)

    async def stop_strategy(self, strategy_id: str) -> None:
        """Stop a running strategy."""
        async with self._lock:
            if strategy_id not in self._strategies:
                return

            strategy = self._strategies[strategy_id]
            if strategy.is_running:
                await strategy.on_stop()

            logger.info("strategy_stopped", strategy_id=strategy_id)

    async def unload_strategy(self, strategy_id: str) -> None:
        """Unload a strategy completely."""
        await self.stop_strategy(strategy_id)

        async with self._lock:
            self._strategies.pop(strategy_id, None)
            self._brokers.pop(strategy_id, None)
            self._configs.pop(strategy_id, None)

            logger.info("strategy_unloaded", strategy_id=strategy_id)

    def get_strategies(self) -> list[dict]:
        """Get list of loaded strategies with status."""
        return [
            {
                "id": s.id,
                "name": s.config.name,
                "symbol": s.config.symbol,
                "exchange": s.config.exchange,
                "interval": s.config.interval,
                "broker": s.config.broker,
                "is_running": s.is_running,
            }
            for s in self._strategies.values()
        ]

    def get_strategy(self, strategy_id: str) -> IStrategy | None:
        """Get strategy by ID."""
        return self._strategies.get(strategy_id)

    @event_handler(BarCompletedEvent)
    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        """Handle bar completed event."""
        strategies = self._find_strategies(
            event.symbol, event.exchange, event.interval, trigger="bar"
        )

        for strategy in strategies:
            try:
                bar = {
                    "symbol": event.symbol,
                    "exchange": event.exchange,
                    "interval": event.interval,
                    "open": event.open,
                    "high": event.high,
                    "low": event.low,
                    "close": event.close,
                    "volume": event.volume,
                    "timestamp": event.bar_start,
                }

                signal = await strategy.on_bar(bar)

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
        """Handle quote received event."""
        strategies = self._find_strategies(
            event.symbol, event.exchange, trigger="tick"
        )

        for strategy in strategies:
            try:
                tick = {
                    "symbol": event.symbol,
                    "exchange": event.exchange,
                    "price": event.price,
                    "volume": event.volume,
                    "timestamp": event.timestamp,
                }

                order = await strategy.on_tick(tick)

                if order:
                    broker = self._brokers.get(strategy.id)
                    if broker:
                        await self._order_manager.submit(order, broker)

            except Exception as e:
                logger.error(
                    "strategy_on_tick_error",
                    strategy_id=strategy.id,
                    error=str(e),
                )

    def _find_strategies(
        self,
        symbol: str,
        exchange: str,
        interval: str | None = None,
        trigger: str = "bar",
    ) -> list[IStrategy]:
        """Find strategies matching symbol/exchange/interval."""
        matches = []
        for strategy in self._strategies.values():
            if not strategy.is_running:
                continue
            if strategy.config.symbol != symbol:
                continue
            if strategy.config.exchange != exchange:
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
        """Process a trading signal through risk and order pipeline."""
        broker = self._brokers.get(strategy.id)
        if not broker:
            logger.warning("no_broker_for_strategy", strategy_id=strategy.id)
            return

        # Get account balance
        balance = await broker.get_balance()

        # Get current position
        position = self._position_tracker.get(strategy.id)

        # Risk check
        valid, reason = self._risk_handler.validate(
            signal, balance, position, strategy.config.risk
        )
        if not valid:
            logger.info(
                "signal_rejected_by_risk",
                strategy_id=strategy.id,
                reason=reason,
            )
            return

        # Calculate position size
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

        # Create order
        order = self._create_order(strategy, signal, size, current_price)

        # Submit order
        result = await self._order_manager.submit(order, broker)

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
        """Create order from signal."""
        side = OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL

        order_type = (
            OrderType.MARKET
            if strategy.config.orders.entry_type == "market"
            else OrderType.LIMIT
        )

        price = signal.entry_price if order_type == OrderType.LIMIT else current_price

        return OrderAggregate.create(
            strategy_id=strategy.id,
            symbol=signal.symbol,
            exchange=signal.exchange,
            side=side,
            order_type=order_type,
            quantity=size,
            price=price,
        )

    async def _get_or_create_broker(self, broker_type: str) -> IBroker:
        """Get existing broker or create new one."""
        # Check if we already have this broker type
        for broker in self._brokers.values():
            if broker.name == broker_type or broker.name == f"{broker_type}-demo":
                return broker

        # Create new broker
        config = self._default_broker_config.copy()
        broker = self._broker_factory.create(broker_type, config)
        return broker


class _DefaultStrategy(IStrategy):
    """Default pass-through strategy that never generates signals."""

    async def on_bar(self, bar: dict) -> Signal | None:
        """Default implementation returns no signal."""
        return None
