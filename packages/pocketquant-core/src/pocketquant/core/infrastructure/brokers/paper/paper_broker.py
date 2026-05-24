"""Paper broker implementation for simulated trading + backtesting.

State machine and LIMIT-pending behavior aligned with Backtrader / QuantConnect.

Order lifecycle: SUBMITTED → FILLED | CANCELLED | REJECTED | EXPIRED
   - MARKET           : SUBMITTED → FILLED  (immediate)
   - LIMIT reachable  : SUBMITTED → FILLED  (immediate, ``limit_immediate``)
   - LIMIT pending    : SUBMITTED → (waits) → FILLED (``limit_cross``)
                                            | CANCELLED (``user_cancel``)
                                            | EXPIRED   (``end_of_run``)
   - REJECT           : SUBMITTED → REJECTED (``insufficient_balance`` / etc.)

Every transition emits an ``OrderEvent`` to subscribers via
``subscribe_order_event``. ``OrderResult`` callbacks continue to fire on every
*fill* (terminal or partial) for backward-compat with existing collectors.

Threading contract: subscriber callbacks are dispatched OUTSIDE ``self._lock``
so they may freely re-enter broker methods without deadlock. State mutations
(positions, balance, pending queue, ``_orders``) happen inside the lock.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.common.messaging import EventBus, event_handler
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.infrastructure.brokers.events import (
    REASON_AUTO_SL,
    REASON_AUTO_TP,
    REASON_END_OF_RUN,
    REASON_INSUFFICIENT_BALANCE,
    REASON_INVALID_LIMIT_PRICE,
    REASON_LIMIT_CROSS,
    REASON_LIMIT_IMMEDIATE,
    REASON_MARKET_FILL,
    REASON_NO_MARKET_PRICE,
    REASON_SUBMIT,
    REASON_USER_CANCEL,
    OrderEvent,
    OrderEventCallback,
)
from pocketquant.core.infrastructure.brokers.interface import IBroker, OrderCallback
from pocketquant.core.infrastructure.brokers.models import AccountBalance, OrderResult

# STOP_LIMIT / STOP_MARKET share the LIMIT pending path until real STOP
# semantics (price-rises-through trigger) are implemented.
# TODO(phase: future): real STOP semantics — BUY STOP fires when bar.high >= stop
_LIMIT_LIKE_TYPES = frozenset({OrderType.LIMIT, OrderType.STOP_LIMIT, OrderType.STOP_MARKET})


@dataclass
class _PendingOrder:
    """Queue entry for a LIMIT-like order waiting to fill on a future bar."""

    order: OrderAggregate
    broker_order_id: str
    submitted_at: datetime
    limit_price: float


class PaperBroker(IBroker):
    """Simulated broker for paper trading and backtesting.

    Features:
    - Configurable slippage simulation
    - Fill delay simulation
    - In-memory position tracking
    - Order callback subscription (fill results)
    - Order *event* (lifecycle) callback subscription — paper-broker only
    - LIMIT non-fill persistence: orders queued and expired at end of run
    - Optional SL/TP auto-fill: when an ``event_bus`` is supplied, the broker
      subscribes to ``BarCompletedEvent`` on ``connect()`` and emits synthetic
      exit fills when ``bar.high``/``bar.low`` crosses a tracked position's
      ``sl_price`` / ``tp_price``. When both SL and TP are hit in the same
      bar, **SL fires first** (deterministic worst-case contract).

    Single-task assumption: callers must not invoke broker methods from
    multiple concurrent tasks. Lock is held only for short state mutations;
    callbacks fire after release.
    """

    def __init__(
        self,
        initial_balance: float = 100_000.0,
        slippage_percent: float = 0.001,  # 0.1% default
        fill_delay_ms: int = 50,
        currency: str = "USDT",
        event_bus: EventBus | None = None,
    ) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._slippage = slippage_percent
        self._fill_delay = fill_delay_ms
        self._currency = currency
        self._event_bus = event_bus

        self._positions: dict[str, PositionAggregate] = {}
        # _orders holds every OrderAggregate observed by submit_order, including
        # REJECTED ones — consumers may enumerate this to build audit lists.
        self._orders: dict[str, OrderAggregate] = {}
        self._order_callbacks: list[OrderCallback] = []
        self._event_callbacks: list[OrderEventCallback] = []
        # Full lifecycle log per order_id — collectors snapshot this at finalize.
        # NOTE: a pending LIMIT carries only the SUBMITTED event until terminal.
        self._order_events: dict[str, list[OrderEvent]] = {}
        # LIMIT-like orders awaiting fill.
        self._pending_orders: dict[str, _PendingOrder] = {}
        self._lock = asyncio.Lock()
        self._connected = False
        self._bar_subscribed = False
        self._current_prices: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "paper"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def slippage(self) -> float:
        return self._slippage

    @slippage.setter
    def slippage(self, value: float) -> None:
        self._slippage = value

    async def connect(self) -> None:
        """Paper broker is always ready. Subscribes to bar events for SL/TP auto-fill."""
        self._connected = True
        if self._event_bus is not None and not self._bar_subscribed:
            # Subscribe LAST so strategy handlers fire first (entry on same bar before exit check).
            self._event_bus.subscribe(BarCompletedEvent, self._on_bar_completed)
            self._bar_subscribed = True

    async def disconnect(self) -> None:
        self._connected = False
        if self._event_bus is not None and self._bar_subscribed:
            self._event_bus.unsubscribe(BarCompletedEvent, self._on_bar_completed)
            self._bar_subscribed = False

    # ----- Order submission ------------------------------------------------

    async def submit_order(self, order: OrderAggregate) -> OrderResult:
        """Route order to MARKET fill, immediate LIMIT, or pending LIMIT queue.

        Lock is held only for state mutation; ``OrderEvent`` and ``OrderResult``
        callbacks fire after release so subscribers may re-enter the broker.
        """
        if self._fill_delay > 0:
            await asyncio.sleep(self._fill_delay / 1000)
        broker_order_id = generate_id_str()
        now = get_current_time()
        pending_events: list[tuple[OrderStatus | None, OrderStatus, str, datetime]] = [
            (None, OrderStatus.SUBMITTED, REASON_SUBMIT, now),
        ]

        if order.order_type in _LIMIT_LIKE_TYPES:
            result, more_events = await self._handle_limit(order, broker_order_id, now)
        else:
            result, more_events = await self._handle_market(order, broker_order_id, now)
        pending_events.extend(more_events)

        # Dispatch events + fill notification AFTER lock-protected mutations.
        for from_s, to_s, reason, when in pending_events:
            await self._emit_event(order.id, from_s, to_s, reason, when=when)
        await self._notify_callbacks(result)
        return result

    async def _handle_market(
        self, order: OrderAggregate, broker_order_id: str, now: datetime
    ) -> tuple[OrderResult, list[tuple[OrderStatus | None, OrderStatus, str, datetime]]]:
        """Fill MARKET immediately, or REJECT. Returns (result, additional_events)."""
        async with self._lock:
            self._orders[order.id] = order
            try:
                base_price = order.price if order.price else self._get_market_price(order)
            except ValueError as e:
                return (
                    OrderResult(
                        order_id=order.id,
                        broker_order_id=broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message=str(e),
                        submitted_at=now,
                        side=order.side,
                    ),
                    [(OrderStatus.SUBMITTED, OrderStatus.REJECTED, REASON_NO_MARKET_PRICE, now)],
                )

            fill_price = self._apply_slippage(base_price, order.side)
            if not self._can_afford(order, fill_price):
                return (
                    OrderResult(
                        order_id=order.id,
                        broker_order_id=broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message="Insufficient balance",
                        submitted_at=now,
                        side=order.side,
                    ),
                    [
                        (
                            OrderStatus.SUBMITTED,
                            OrderStatus.REJECTED,
                            REASON_INSUFFICIENT_BALANCE,
                            now,
                        )
                    ],
                )

            self._execute_fill(order, fill_price)
            result = OrderResult(
                order_id=order.id,
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                filled_price=fill_price,
                submitted_at=now,
                sl_price=order.sl_price,
                tp_price=order.tp_price,
                side=order.side,
            )
            return (result, [(OrderStatus.SUBMITTED, OrderStatus.FILLED, REASON_MARKET_FILL, now)])

    async def _handle_limit(
        self, order: OrderAggregate, broker_order_id: str, now: datetime
    ) -> tuple[OrderResult, list[tuple[OrderStatus | None, OrderStatus, str, datetime]]]:
        """Fill LIMIT immediately if price crosses; else queue as pending."""
        async with self._lock:
            self._orders[order.id] = order
            if order.price is None:
                return (
                    OrderResult(
                        order_id=order.id,
                        broker_order_id=broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message="LIMIT order requires price",
                        submitted_at=now,
                        side=order.side,
                    ),
                    [
                        (
                            OrderStatus.SUBMITTED,
                            OrderStatus.REJECTED,
                            REASON_INVALID_LIMIT_PRICE,
                            now,
                        )
                    ],
                )

            cur = self._current_prices.get(order.symbol.upper())
            if cur is not None and self._limit_crosses(order.side, order.price, cur):
                fill_price = self._apply_slippage(order.price, order.side)
                if not self._can_afford(order, fill_price):
                    return (
                        OrderResult(
                            order_id=order.id,
                            broker_order_id=broker_order_id,
                            status=OrderStatus.REJECTED,
                            error_message="Insufficient balance",
                            submitted_at=now,
                            side=order.side,
                        ),
                        [
                            (
                                OrderStatus.SUBMITTED,
                                OrderStatus.REJECTED,
                                REASON_INSUFFICIENT_BALANCE,
                                now,
                            )
                        ],
                    )
                self._execute_fill(order, fill_price)
                result = OrderResult(
                    order_id=order.id,
                    broker_order_id=broker_order_id,
                    status=OrderStatus.FILLED,
                    filled_quantity=order.quantity,
                    filled_price=fill_price,
                    submitted_at=now,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                    side=order.side,
                )
                return (
                    result,
                    [(OrderStatus.SUBMITTED, OrderStatus.FILLED, REASON_LIMIT_IMMEDIATE, now)],
                )

            self._pending_orders[order.id] = _PendingOrder(
                order=order,
                broker_order_id=broker_order_id,
                submitted_at=now,
                limit_price=order.price,
            )
            return (
                OrderResult(
                    order_id=order.id,
                    broker_order_id=broker_order_id,
                    status=OrderStatus.SUBMITTED,
                    filled_quantity=0.0,
                    submitted_at=now,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                    side=order.side,
                ),
                [],
            )

    # ----- Cancel / expire -------------------------------------------------

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel a pending LIMIT. Idempotent for already-filled orders."""
        async with self._lock:
            pending_id: str | None = None
            for oid, pending in self._pending_orders.items():
                if pending.broker_order_id == broker_order_id:
                    pending_id = oid
                    break
            if pending_id is None:
                return True
            pending = self._pending_orders.pop(pending_id)
            when = get_current_time()
            result = OrderResult(
                order_id=pending_id,
                broker_order_id=pending.broker_order_id,
                status=OrderStatus.CANCELLED,
                filled_quantity=0.0,
                submitted_at=pending.submitted_at,
                side=pending.order.side,
            )
        await self._emit_event(
            pending_id,
            OrderStatus.SUBMITTED,
            OrderStatus.CANCELLED,
            REASON_USER_CANCEL,
            when=when,
        )
        await self._notify_callbacks(result)
        return True

    async def expire_pending_orders(self) -> int:
        """Mark all still-pending LIMIT orders as EXPIRED. Returns count expired.

        Called by ``BacktestAppService`` after replay completes so each non-fill
        LIMIT has a terminal state recorded (forward-test parity). OrderResults
        with status=EXPIRED are delivered via ``subscribe_order_updates``.
        """
        async with self._lock:
            pendings = list(self._pending_orders.values())
            self._pending_orders.clear()
            when = get_current_time()

        for pending in pendings:
            await self._emit_event(
                pending.order.id,
                OrderStatus.SUBMITTED,
                OrderStatus.EXPIRED,
                REASON_END_OF_RUN,
                when=when,
            )
            result = OrderResult(
                order_id=pending.order.id,
                broker_order_id=pending.broker_order_id,
                status=OrderStatus.EXPIRED,
                filled_quantity=0.0,
                submitted_at=pending.submitted_at,
                side=pending.order.side,
            )
            await self._notify_callbacks(result)
        return len(pendings)

    # ----- Queries ---------------------------------------------------------

    async def get_positions(self) -> list[PositionAggregate]:
        async with self._lock:
            return [p for p in self._positions.values() if not p.is_closed]

    async def get_balance(self) -> AccountBalance:
        async with self._lock:
            unrealized = sum(p.unrealized_pnl for p in self._positions.values() if not p.is_closed)
            return AccountBalance(
                total_equity=self._balance + unrealized,
                available_balance=self._balance,
                currency=self._currency,
                unrealized_pnl=unrealized,
            )

    def get_order_events(self, order_id: str) -> list[OrderEvent]:
        """Return the full lifecycle event log for an order (copy).

        A still-pending LIMIT carries only the initial SUBMITTED event until
        it reaches a terminal state (FILLED / CANCELLED / EXPIRED).
        """
        return list(self._order_events.get(order_id, []))

    # ----- Subscription API -----------------------------------------------

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        """Add order *fill / status-result* callback."""
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        """Clear all order callbacks."""
        self._order_callbacks.clear()

    async def subscribe_order_event(self, callback: OrderEventCallback) -> None:
        """Add order *lifecycle event* callback (paper broker only)."""
        self._event_callbacks.append(callback)

    async def unsubscribe_order_event(self) -> None:
        """Clear all order event callbacks."""
        self._event_callbacks.clear()

    # ----- Price tracking --------------------------------------------------

    def set_current_price(self, symbol: str, price: float) -> None:
        self._current_prices[symbol.upper()] = price

    # ----- Internals -------------------------------------------------------

    def _get_market_price(self, order: OrderAggregate) -> float:
        if order.price:
            return order.price
        symbol_upper = order.symbol.upper()
        if symbol_upper in self._current_prices:
            return self._current_prices[symbol_upper]
        position_key = f"{order.strategy_id}:{order.symbol}"
        if position_key in self._positions:
            pos = self._positions[position_key]
            if pos.current_price > 0:
                return pos.current_price
        raise ValueError(
            f"No market price available for {order.symbol}. "
            "Market orders require price context from strategy signal."
        )

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        if side == OrderSide.BUY:
            return price * (1 + self._slippage)
        return price * (1 - self._slippage)

    def _can_afford(self, order: OrderAggregate, fill_price: float) -> bool:
        if order.side != OrderSide.BUY:
            return True
        return fill_price * order.quantity <= self._balance

    @staticmethod
    def _limit_crosses(side: OrderSide, limit_price: float, market_price: float) -> bool:
        if side == OrderSide.BUY:
            return market_price <= limit_price
        return market_price >= limit_price

    @staticmethod
    def _limit_crosses_bar(side: OrderSide, limit_price: float, high: float, low: float) -> bool:
        if side == OrderSide.BUY:
            return low <= limit_price
        return high >= limit_price

    def _execute_fill(self, order: OrderAggregate, fill_price: float) -> None:
        """Update balance and positions based on fill. MUST be called under lock."""
        position_key = f"{order.strategy_id}:{order.symbol}"
        order_value = fill_price * order.quantity

        if order.side == OrderSide.BUY:
            self._balance -= order_value
            if position_key in self._positions:
                pos = self._positions[position_key]
                if pos.side == PositionSide.LONG:
                    pos.add_quantity(order.quantity, fill_price)
                else:
                    pos.reduce_quantity(order.quantity, fill_price)
                    self._balance += pos.realized_pnl
            else:
                self._positions[position_key] = PositionAggregate.open(
                    strategy_id=order.strategy_id,
                    symbol=order.symbol,
                    side=PositionSide.LONG,
                    entry_price=fill_price,
                    quantity=order.quantity,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                )
        else:  # SELL
            self._balance += order_value
            if position_key in self._positions:
                pos = self._positions[position_key]
                if pos.side == PositionSide.LONG:
                    pos.reduce_quantity(order.quantity, fill_price)
                    self._balance += pos.realized_pnl
                else:
                    pos.add_quantity(order.quantity, fill_price)
            else:
                self._positions[position_key] = PositionAggregate.open(
                    strategy_id=order.strategy_id,
                    symbol=order.symbol,
                    side=PositionSide.SHORT,
                    entry_price=fill_price,
                    quantity=order.quantity,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                )

    async def _emit_event(
        self,
        order_id: str,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        reason: str,
        when: datetime | None = None,
    ) -> None:
        """Append an OrderEvent to the per-order log and dispatch to subscribers.

        ``when`` defaults to simulation time so persisted events carry the
        bar's replay timestamp during backtests, not wall-clock.
        """
        event = OrderEvent(
            timestamp=when or get_current_time(),
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )
        self._order_events.setdefault(order_id, []).append(event)
        errors: list[Exception] = []
        for cb in self._event_callbacks:
            try:
                ret = cb(order_id, event)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception as e:
                errors.append(e)
        if errors:
            raise errors[0]

    async def _notify_callbacks(self, result: OrderResult) -> None:
        """Notify all fill-result callbacks. First raised error re-raised after dispatch."""
        errors: list[Exception] = []
        for callback in self._order_callbacks:
            try:
                ret = callback(result)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception as e:
                errors.append(e)
        if errors:
            raise errors[0]

    # ----- Bar-driven flows -----------------------------------------------

    @event_handler(BarCompletedEvent)
    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        """Auto-fill pending LIMITs + SL/TP exits as the bar resolves.

        Order: pending-LIMIT fills first (entries may open the very position
        that the same bar's SL/TP would then close in extreme moves), then
        SL/TP scans existing positions. Strategy entry handlers still run
        before this because the broker subscribes LAST (see ``connect``).
        """
        self._current_prices[event.symbol.upper()] = event.close

        await self._fill_pending_on_bar(event)

        to_close: list[tuple[PositionAggregate, float, OrderSide, str]] = []
        async with self._lock:
            for pos in self._positions.values():
                if pos.is_closed or pos.symbol != event.symbol:
                    continue
                if pos.sl_price is None and pos.tp_price is None:
                    continue
                hit = self._check_sl_tp(pos, event.high, event.low)
                if hit is not None:
                    exit_price, exit_side, reason = hit
                    to_close.append((pos, exit_price, exit_side, reason))

        for pos, exit_price, exit_side, reason in to_close:
            await self._fire_synthetic_exit(pos, exit_price, exit_side, reason)

    async def _fill_pending_on_bar(self, event: BarCompletedEvent) -> None:
        """Scan pending LIMITs against this bar's range; fill any that cross."""
        to_fill: list[_PendingOrder] = []
        async with self._lock:
            for pending in list(self._pending_orders.values()):
                if pending.order.symbol != event.symbol:
                    continue
                if self._limit_crosses_bar(
                    pending.order.side, pending.limit_price, event.high, event.low
                ):
                    to_fill.append(pending)
                    del self._pending_orders[pending.order.id]

        when = get_current_time()
        for pending in to_fill:
            fill_price = self._apply_slippage(pending.limit_price, pending.order.side)
            async with self._lock:
                if not self._can_afford(pending.order, fill_price):
                    event_args: tuple[OrderStatus, OrderStatus, str] = (
                        OrderStatus.SUBMITTED,
                        OrderStatus.REJECTED,
                        REASON_INSUFFICIENT_BALANCE,
                    )
                    result = OrderResult(
                        order_id=pending.order.id,
                        broker_order_id=pending.broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message="Insufficient balance",
                        submitted_at=pending.submitted_at,
                        side=pending.order.side,
                    )
                else:
                    self._execute_fill(pending.order, fill_price)
                    event_args = (
                        OrderStatus.SUBMITTED,
                        OrderStatus.FILLED,
                        REASON_LIMIT_CROSS,
                    )
                    result = OrderResult(
                        order_id=pending.order.id,
                        broker_order_id=pending.broker_order_id,
                        status=OrderStatus.FILLED,
                        filled_quantity=pending.order.quantity,
                        filled_price=fill_price,
                        submitted_at=pending.submitted_at,
                        sl_price=pending.order.sl_price,
                        tp_price=pending.order.tp_price,
                        side=pending.order.side,
                    )
            await self._emit_event(pending.order.id, *event_args, when=when)
            await self._notify_callbacks(result)

    def _check_sl_tp(
        self, pos: PositionAggregate, bar_high: float, bar_low: float
    ) -> tuple[float, OrderSide, str] | None:
        """Return (trigger_price, exit_side, reason) if SL/TP fires; SL wins ties."""
        sl, tp = pos.sl_price, pos.tp_price
        if pos.side == PositionSide.LONG:
            if sl is not None and bar_low <= sl:
                return (sl, OrderSide.SELL, REASON_AUTO_SL)
            if tp is not None and bar_high >= tp:
                return (tp, OrderSide.SELL, REASON_AUTO_TP)
        else:  # SHORT
            if sl is not None and bar_high >= sl:
                return (sl, OrderSide.BUY, REASON_AUTO_SL)
            if tp is not None and bar_low <= tp:
                return (tp, OrderSide.BUY, REASON_AUTO_TP)
        return None

    async def _fire_synthetic_exit(
        self,
        pos: PositionAggregate,
        trigger_price: float,
        exit_side: OrderSide,
        reason: str,
    ) -> None:
        """Build a synthetic market exit + emit SUBMITTED→FILLED event pair."""
        fill_price = self._apply_slippage(trigger_price, exit_side)
        exit_order = OrderAggregate.create(
            strategy_id=pos.strategy_id,
            symbol=pos.symbol,
            side=exit_side,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            price=trigger_price,
        )
        broker_order_id = generate_id_str()
        now = get_current_time()
        async with self._lock:
            self._execute_fill(exit_order, fill_price)
            self._orders[exit_order.id] = exit_order
            result = OrderResult(
                order_id=exit_order.id,
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=exit_order.quantity,
                filled_price=fill_price,
                submitted_at=now,
                sl_price=None,
                tp_price=None,
                side=exit_side,
            )
        await self._emit_event(exit_order.id, None, OrderStatus.SUBMITTED, REASON_SUBMIT, when=now)
        await self._emit_event(
            exit_order.id, OrderStatus.SUBMITTED, OrderStatus.FILLED, reason, when=now
        )
        await self._notify_callbacks(result)

    def reset(self) -> None:
        """Reset broker to initial state (for backtesting)."""
        self._balance = self._initial_balance
        self._positions.clear()
        self._orders.clear()
        self._current_prices.clear()
        self._order_events.clear()
        self._pending_orders.clear()
