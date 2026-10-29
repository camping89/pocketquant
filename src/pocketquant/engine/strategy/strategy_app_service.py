import asyncio
from typing import TYPE_CHECKING

import structlog

from pocketquant.core.common.messaging import EventBus
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
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.risk import PositionCalculatorDomainService
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from pocketquant.core.domain.symbol import ContractSpec
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

if TYPE_CHECKING:
    from pocketquant.engine.execution.order_app_service import OrderAppService
    from pocketquant.engine.execution.position_app_service import PositionAppService
    from pocketquant.engine.execution.risk_check import RiskCheckHandler

logger = structlog.get_logger(__name__)

# Stop distance used for sizing when a signal carries no stop-loss price.
_FALLBACK_SL_PCT = 0.01


class StrategyAppService:
    """Engine for managing and executing trading strategies.

    Subscribes to market events and dispatches to registered strategies.
    Coordinates signal processing through risk checks and order submission.
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker_factory: IBrokerFactoryPort,
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

        self._strategies: dict[str, IStrategyService] = {}
        self._brokers: dict[str, IBrokerPort] = {}
        # Paper pools per contract spec (it prices every fill with one spec, so an
        # XAUUSD subscription cannot share the crypto paper account); a venue broker
        # pools per type, with no spec in its key.
        self._broker_pool: dict[tuple[str, ContractSpec | None], IBrokerPort] = {}
        self._configs: dict[str, StrategyConfig] = {}
        self._running = False
        self._lock = asyncio.Lock()

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
        strategies = self._find_strategies(event.symbol, event.interval)

        for strategy in strategies:
            signal = None
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
                if signal:
                    await self._notify_rejected(strategy, str(e))

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
        self, strategy: IStrategyService, signal: Signal, current_price: float
    ) -> None:
        broker = self._brokers.get(strategy.id)
        if not broker:
            logger.warning("no_broker_for_strategy", strategy_id=strategy.id)
            await strategy.on_order_rejected("no broker")
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

        result = await self._order_app_service.submit(order, broker)
        if not result.is_success:
            await strategy.on_order_rejected(result.error_message or "rejected")

        logger.debug(
            "signal_processed",
            strategy_id=strategy.id,
            direction=signal.direction.value,
            size=size,
            order_status=result.status.value,
        )

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
