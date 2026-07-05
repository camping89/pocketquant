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
from pocketquant.core.domain.brokers.broker_port import (
    IBrokerPort,
    OrderCallback,
    TradeCallback,
)
from pocketquant.core.domain.brokers.events import (
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
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import (
    PositionAggregate,
    PositionSide,
    TradeClosedEvent,
)
from pocketquant.core.domain.trading import CommissionModel, PercentageCommissionModel

# STOP_LIMIT / STOP_MARKET share the LIMIT pending path until real STOP
# semantics (price-rises-through trigger) are implemented.
# TODO(phase: future): real STOP semantics — BUY STOP fires when bar.high >= stop
_LIMIT_LIKE_TYPES = frozenset({OrderType.LIMIT, OrderType.STOP_LIMIT, OrderType.STOP_MARKET})

# (from_status, to_status, reason, when) transitions emitted after a lock section.
_StatusEvents = list[tuple[OrderStatus | None, OrderStatus, str, datetime]]
# What a fill-handler hands back to submit_order: the result, its status
# transitions, and any trade closures to forward after the fill notify.
_FillOutcome = tuple[OrderResult, _StatusEvents, list[TradeClosedEvent]]


@dataclass
class _PendingOrder:
    """Queue entry for a LIMIT-like order waiting to fill on a future bar."""

    order: OrderAggregate
    broker_order_id: str
    submitted_at: datetime
    limit_price: float


class PaperBrokerAdapter(IBrokerPort):
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
        initial_balance: float = 10_000.0,
        slippage_percent: float = 0.001,  # 0.1% default
        fill_delay_ms: int = 50,
        currency: str = "USD",
        event_bus: EventBus | None = None,
        commission_model: CommissionModel | None = None,
    ) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._slippage = slippage_percent
        self._fill_delay = fill_delay_ms
        self._currency = currency
        self._event_bus = event_bus
        # Default bps=0 keeps pre-R3 balances when no model is injected; real bps
        # (backtest commission_bps / live paper_commission_percent) wired via factory.
        self._commission_model = commission_model or PercentageCommissionModel(bps=0.0)

        self._positions: dict[str, PositionAggregate] = {}
        # _orders holds every OrderAggregate observed by submit_order, including
        # REJECTED ones — consumers may enumerate this to build audit lists.
        self._orders: dict[str, OrderAggregate] = {}
        self._order_callbacks: list[OrderCallback] = []
        self._trade_callbacks: list[TradeCallback] = []
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
            result, more_events, trades = await self._handle_limit(order, broker_order_id, now)
        else:
            result, more_events, trades = await self._handle_market(order, broker_order_id, now)
        pending_events.extend(more_events)

        # Dispatch events + fill notification AFTER lock-protected mutations.
        for from_s, to_s, reason, when in pending_events:
            await self._emit_event(str(order.id), from_s, to_s, reason, when=when)
        await self._notify_callbacks(result)
        # Trade closures fire AFTER the fill so subscribers back-link the order.
        for trade in trades:
            await self._notify_trade_callbacks(trade)
        return result

    async def _handle_market(
        self, order: OrderAggregate, broker_order_id: str, now: datetime
    ) -> _FillOutcome:
        async with self._lock:
            self._orders[str(order.id)] = order
            try:
                base_price = order.price if order.price else self._get_market_price(order)
            except ValueError as e:
                return (
                    OrderResult(
                        order_id=str(order.id),
                        broker_order_id=broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message=str(e),
                        submitted_at=now,
                        side=order.side,
                    ),
                    [(OrderStatus.SUBMITTED, OrderStatus.REJECTED, REASON_NO_MARKET_PRICE, now)],
                    [],
                )

            fill_price = self._apply_slippage(base_price, order.side)
            if not self._can_afford(order, fill_price):
                return (
                    OrderResult(
                        order_id=str(order.id),
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
                    [],
                )

            commission, trades = self._execute_fill_with_commission(order, fill_price)
            result = OrderResult(
                order_id=str(order.id),
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                filled_price=fill_price,
                submitted_at=now,
                sl_price=order.sl_price,
                tp_price=order.tp_price,
                side=order.side,
                commission=commission,
            )
            return (
                result,
                [(OrderStatus.SUBMITTED, OrderStatus.FILLED, REASON_MARKET_FILL, now)],
                trades,
            )

    async def _handle_limit(
        self, order: OrderAggregate, broker_order_id: str, now: datetime
    ) -> _FillOutcome:
        async with self._lock:
            self._orders[str(order.id)] = order
            if order.price is None:
                return (
                    OrderResult(
                        order_id=str(order.id),
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
                    [],
                )

            cur = self._current_prices.get(order.symbol.upper())
            if cur is not None and self._limit_crosses(order.side, order.price, cur):
                fill_price = self._apply_slippage(order.price, order.side)
                if not self._can_afford(order, fill_price):
                    return (
                        OrderResult(
                            order_id=str(order.id),
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
                        [],
                    )
                commission, trades = self._execute_fill_with_commission(order, fill_price)
                result = OrderResult(
                    order_id=str(order.id),
                    broker_order_id=broker_order_id,
                    status=OrderStatus.FILLED,
                    filled_quantity=order.quantity,
                    filled_price=fill_price,
                    submitted_at=now,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                    side=order.side,
                    commission=commission,
                )
                return (
                    result,
                    [(OrderStatus.SUBMITTED, OrderStatus.FILLED, REASON_LIMIT_IMMEDIATE, now)],
                    trades,
                )

            self._pending_orders[str(order.id)] = _PendingOrder(
                order=order,
                broker_order_id=broker_order_id,
                submitted_at=now,
                limit_price=order.price,
            )
            return (
                OrderResult(
                    order_id=str(order.id),
                    broker_order_id=broker_order_id,
                    status=OrderStatus.SUBMITTED,
                    filled_quantity=0.0,
                    submitted_at=now,
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                    side=order.side,
                ),
                [],
                [],
            )

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
                str(pending.order.id),
                OrderStatus.SUBMITTED,
                OrderStatus.EXPIRED,
                REASON_END_OF_RUN,
                when=when,
            )
            result = OrderResult(
                order_id=str(pending.order.id),
                broker_order_id=pending.broker_order_id,
                status=OrderStatus.EXPIRED,
                filled_quantity=0.0,
                submitted_at=pending.submitted_at,
                side=pending.order.side,
            )
            await self._notify_callbacks(result)
        return len(pendings)

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

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        """Add order *fill / status-result* callback."""
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        """Clear all order callbacks."""
        self._order_callbacks.clear()

    async def subscribe_trades(self, callback: TradeCallback) -> None:
        """Add round-trip trade-closure callback."""
        self._trade_callbacks.append(callback)

    async def unsubscribe_trades(self) -> None:
        """Clear all trade callbacks."""
        self._trade_callbacks.clear()

    async def subscribe_order_event(self, callback: OrderEventCallback) -> None:
        """Add order *lifecycle event* callback (paper broker only)."""
        self._event_callbacks.append(callback)

    async def unsubscribe_order_event(self) -> None:
        """Clear all order event callbacks."""
        self._event_callbacks.clear()

    def set_current_price(self, symbol: str, price: float) -> None:
        self._current_prices[symbol.upper()] = price

    def _get_market_price(self, order: OrderAggregate) -> float:
        if order.price:
            return order.price
        symbol_upper = order.symbol.upper()
        if symbol_upper in self._current_prices:
            return self._current_prices[symbol_upper]
        position_key = f"{order.subscription_id}:{order.symbol}"
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

    def _commission(self, fill_price: float, quantity: float) -> float:
        return self._commission_model.compute(fill_price, quantity)

    def _can_afford(self, order: OrderAggregate, fill_price: float) -> bool:
        if order.side != OrderSide.BUY:
            return True
        # A BUY that reduces/covers an existing short consumes no margin under the
        # futures model, so it must never be gated by notional vs cash — otherwise
        # a losing short whose cover notional exceeds balance gets stuck open. Such
        # a cover still debits commission on fill (below), so balance can dip
        # slightly negative in the pathological cover-with-empty-cash case — accepted.
        position_key = f"{order.subscription_id}:{order.symbol}"
        existing = self._positions.get(position_key)
        if existing is not None and not existing.is_closed and existing.side == PositionSide.SHORT:
            return True
        commission = self._commission(fill_price, order.quantity)
        return fill_price * order.quantity + commission <= self._balance

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

    def _execute_fill(
        self, order: OrderAggregate, fill_price: float, commission: float
    ) -> list[TradeClosedEvent]:
        """Apply a fill under the futures/margin model. MUST be called under lock.

        Opening or adding to a position does not move cash (no notional debit);
        balance changes only by realized-pnl delta when a position is reduced or
        closed. ``reduce_quantity`` accumulates into ``position.realized_pnl``, so
        each reduce credits the delta since the prior call — crediting the
        cumulative value would multi-count on partial closes.

        ``commission`` is threaded as entry-side (open/add) or exit-side (reduce)
        per the single fill's role, then the mutated position is drained and its
        ``TradeClosedEvent`` closures returned for the caller to forward.
        """
        position_key = f"{order.subscription_id}:{order.symbol}"
        order_id = str(order.id)

        # A closed position lingers in the dict under its key; a re-entry fill
        # must open a fresh position rather than mutate the closed one (which
        # raises). Treat closed as absent so round-trip → re-entry works.
        existing = self._positions.get(position_key)
        live = existing if existing is not None and not existing.is_closed else None

        if order.side == OrderSide.BUY:
            if live is not None:
                if live.side == PositionSide.LONG:
                    live.add_quantity(order.quantity, fill_price, commission=commission)
                else:  # BUY reduces/covers a short
                    self._reduce_and_credit(live, order.quantity, fill_price, commission, order_id)
                target = live
            else:
                target = self._open_position(order, PositionSide.LONG, fill_price, commission)
                self._positions[position_key] = target
        else:  # SELL
            if live is not None:
                if live.side == PositionSide.LONG:  # SELL reduces/closes a long
                    self._reduce_and_credit(live, order.quantity, fill_price, commission, order_id)
                else:
                    live.add_quantity(order.quantity, fill_price, commission=commission)
                target = live
            else:
                target = self._open_position(order, PositionSide.SHORT, fill_price, commission)
                self._positions[position_key] = target

        return [e for e in target.collect_events() if isinstance(e, TradeClosedEvent)]

    def _open_position(
        self,
        order: OrderAggregate,
        side: PositionSide,
        fill_price: float,
        commission: float,
    ) -> PositionAggregate:
        # opened_at pinned to sim-time so backtest durations reflect bar replay,
        # not wall-clock (position now lives in open_positions via opened_at).
        return PositionAggregate.open(
            subscription_id=order.subscription_id,
            symbol=order.symbol,
            side=side,
            entry_price=fill_price,
            quantity=order.quantity,
            sl_price=order.sl_price,
            tp_price=order.tp_price,
            entry_order_id=str(order.id),
            entry_commission=commission,
            opened_at=get_current_time(),
        )

    def _execute_fill_with_commission(
        self, order: OrderAggregate, fill_price: float
    ) -> tuple[float, list[TradeClosedEvent]]:
        """Apply a fill then debit its commission. MUST be called under lock.

        Single debit point for all four fill paths so no path can silently skip
        commission. Commission computed BEFORE the fill so it can be threaded into
        the position as entry/exit cost. Returns ``(commission, trades)`` so
        callers stamp OrderResult and forward trade closures after the fill notify.
        """
        commission = self._commission(fill_price, order.quantity)
        trades = self._execute_fill(order, fill_price, commission)
        self._balance -= commission
        return commission, trades

    def _reduce_and_credit(
        self,
        position: PositionAggregate,
        quantity: float,
        fill_price: float,
        exit_commission: float = 0.0,
        exit_order_id: str | None = None,
    ) -> None:
        before = position.realized_pnl
        position.reduce_quantity(
            quantity,
            fill_price,
            exit_commission=exit_commission,
            exit_order_id=exit_order_id,
            exit_time=get_current_time(),
        )
        self._balance += position.realized_pnl - before

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
        # Dispatch to every callback even if one raises; re-raise the first error after.
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

    async def _notify_trade_callbacks(self, trade: TradeClosedEvent) -> None:
        # Fired AFTER the fill OrderResult so subscribers can back-link the order.
        errors: list[Exception] = []
        for callback in self._trade_callbacks:
            try:
                ret = callback(trade)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception as e:
                errors.append(e)
        if errors:
            raise errors[0]

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

        # Mark surviving positions to the bar close so unrealized_pnl (and thus
        # total_equity in get_balance) tracks price per bar. Runs after SL/TP so
        # exited positions aren't re-marked. BacktestAppService._mtm_on_bar
        # subscribes after this handler, so it reads the freshly marked equity.
        async with self._lock:
            for pos in self._positions.values():
                if not pos.is_closed and pos.symbol == event.symbol:
                    pos.update_price(event.close)

    async def _fill_pending_on_bar(self, event: BarCompletedEvent) -> None:
        to_fill: list[_PendingOrder] = []
        async with self._lock:
            for pending in list(self._pending_orders.values()):
                if pending.order.symbol != event.symbol:
                    continue
                if self._limit_crosses_bar(
                    pending.order.side, pending.limit_price, event.high, event.low
                ):
                    to_fill.append(pending)
                    del self._pending_orders[str(pending.order.id)]

        when = get_current_time()
        for pending in to_fill:
            fill_price = self._apply_slippage(pending.limit_price, pending.order.side)
            trades: list[TradeClosedEvent] = []
            async with self._lock:
                if not self._can_afford(pending.order, fill_price):
                    event_args: tuple[OrderStatus, OrderStatus, str] = (
                        OrderStatus.SUBMITTED,
                        OrderStatus.REJECTED,
                        REASON_INSUFFICIENT_BALANCE,
                    )
                    result = OrderResult(
                        order_id=str(pending.order.id),
                        broker_order_id=pending.broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message="Insufficient balance",
                        submitted_at=pending.submitted_at,
                        side=pending.order.side,
                    )
                else:
                    commission, trades = self._execute_fill_with_commission(
                        pending.order, fill_price
                    )
                    event_args = (
                        OrderStatus.SUBMITTED,
                        OrderStatus.FILLED,
                        REASON_LIMIT_CROSS,
                    )
                    result = OrderResult(
                        order_id=str(pending.order.id),
                        broker_order_id=pending.broker_order_id,
                        status=OrderStatus.FILLED,
                        filled_quantity=pending.order.quantity,
                        filled_price=fill_price,
                        submitted_at=pending.submitted_at,
                        sl_price=pending.order.sl_price,
                        tp_price=pending.order.tp_price,
                        side=pending.order.side,
                        commission=commission,
                    )
            await self._emit_event(str(pending.order.id), *event_args, when=when)
            await self._notify_callbacks(result)
            for trade in trades:
                await self._notify_trade_callbacks(trade)

    def _check_sl_tp(
        self, pos: PositionAggregate, bar_high: float, bar_low: float
    ) -> tuple[float, OrderSide, str] | None:
        # SL checked before TP so SL wins when a single bar straddles both levels.
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
        fill_price = self._apply_slippage(trigger_price, exit_side)
        exit_order = OrderAggregate.create(
            subscription_id=pos.subscription_id,
            symbol=pos.symbol,
            side=exit_side,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            price=trigger_price,
        )
        broker_order_id = generate_id_str()
        now = get_current_time()
        async with self._lock:
            commission, trades = self._execute_fill_with_commission(exit_order, fill_price)
            self._orders[str(exit_order.id)] = exit_order
            result = OrderResult(
                order_id=str(exit_order.id),
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=exit_order.quantity,
                filled_price=fill_price,
                submitted_at=now,
                sl_price=None,
                tp_price=None,
                side=exit_side,
                commission=commission,
            )
        await self._emit_event(
            str(exit_order.id), None, OrderStatus.SUBMITTED, REASON_SUBMIT, when=now
        )
        await self._emit_event(
            str(exit_order.id), OrderStatus.SUBMITTED, OrderStatus.FILLED, reason, when=now
        )
        await self._notify_callbacks(result)
        for trade in trades:
            await self._notify_trade_callbacks(trade)
        # Synthetic exits never pass through order_app_service, so publish the
        # fill here too — the strategy's on_order_filled reset depends on this
        # opposite-side exit event. Entry fills already publish via submit().
        if self._event_bus is not None:
            await self._event_bus.publish(
                OrderFilledEvent(
                    order_id=str(exit_order.id),
                    subscription_id=pos.subscription_id,
                    symbol=pos.symbol,
                    side=exit_side,
                    filled_quantity=exit_order.quantity,
                    filled_price=fill_price,
                )
            )

    def reset(self) -> None:
        self._balance = self._initial_balance
        self._positions.clear()
        self._orders.clear()
        self._current_prices.clear()
        self._order_events.clear()
        self._pending_orders.clear()
