import asyncio
from dataclasses import replace
from datetime import datetime

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
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
    REASON_CANCELLED,
    REASON_INSUFFICIENT_BALANCE,
    REASON_MARKET_FILL,
    REASON_NO_MARKET_PRICE,
    REASON_STOP_FILL,
    REASON_SUBMIT,
    REASON_UNSUPPORTED_ORDER_TYPE,
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
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.core.domain.trading import CommissionModel, PercentageCommissionModel

logger = get_logger(__name__)

# (from_status, to_status, reason, when) transitions emitted after a lock section.
_StatusEvents = list[tuple[OrderStatus | None, OrderStatus, str, datetime]]
# What a fill-handler hands back to submit_order: the result, its status
# transitions, and any trade closures to forward after the fill notify.
_FillOutcome = tuple[OrderResult, _StatusEvents, list[TradeClosedEvent]]
# (position, exit trigger price, exit side, reason) of a synthetic exit to fire.
_Exit = tuple[PositionAggregate, float, OrderSide, str]


# Callers must not use one broker from several concurrent tasks. Subscriber callbacks
# run outside self._lock so they may re-enter broker methods without deadlock.
class PaperBrokerAdapter(IBrokerPort):
    def __init__(
        self,
        initial_balance: float = 10_000.0,
        slippage_percent: float = 0.001,  # 0.1% default
        fill_delay_ms: int = 50,
        currency: str = "USD",
        event_bus: EventBus | None = None,
        commission_model: CommissionModel | None = None,
        contract_spec: ContractSpec = LINEAR_SPEC,
        spread: float = 0.0,
    ) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._slippage = slippage_percent
        self._fill_delay = fill_delay_ms
        self._currency = currency
        self._event_bus = event_bus
        # Default bps=0 keeps pre-R3 balances when no model is injected; real bps
        # (backtest commission_bps / live paper_commission_bps) wired via factory.
        self._commission_model = commission_model or PercentageCommissionModel(bps=0.0)
        # Positions opened here realize PnL in account currency via this multiplier.
        self._contract_spec = contract_spec
        # Bars are bid prices; ask = bid + spread for BUY fills and SHORT SL/TP triggers.
        self._spread = spread

        self._positions: dict[str, PositionAggregate] = {}
        self._order_callbacks: list[OrderCallback] = []
        self._trade_callbacks: list[TradeCallback] = []
        self._event_callbacks: list[OrderEventCallback] = []
        # Full lifecycle log per order_id — collectors snapshot this at finalize.
        self._order_events: dict[str, list[OrderEvent]] = {}
        self._lock = asyncio.Lock()
        self._connected = False
        self._bar_subscribed = False
        self._current_prices: dict[str, float] = {}
        # Finest interval seen per symbol: a coarser bar's range starts before
        # entries made inside it, so only the finest stream fills or exits.
        self._finest_interval_s: dict[str, int] = {}
        # Resting STOP_MARKET orders by broker order id, with the time each was placed.
        self._resting: dict[str, tuple[OrderAggregate, datetime]] = {}

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

    async def submit_order(
        self, order: OrderAggregate, *, deadline: datetime | None = None
    ) -> OrderResult:
        if self._fill_delay > 0:
            await asyncio.sleep(self._fill_delay / 1000)
        broker_order_id = generate_id_str()
        now = get_current_time()
        pending_events: list[tuple[OrderStatus | None, OrderStatus, str, datetime]] = [
            (None, OrderStatus.SUBMITTED, REASON_SUBMIT, now),
        ]

        if order.order_type is OrderType.STOP_MARKET:
            async with self._lock:
                self._resting[broker_order_id] = (order, now)
            result = OrderResult(
                order_id=str(order.id),
                broker_order_id=broker_order_id,
                status=OrderStatus.SUBMITTED,
                submitted_at=now,
                sl_price=order.sl_price,
                tp_price=order.tp_price,
                side=order.side,
            )
            trades: list[TradeClosedEvent] = []
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
            if order.order_type is not OrderType.MARKET:
                return (
                    OrderResult(
                        order_id=str(order.id),
                        broker_order_id=broker_order_id,
                        status=OrderStatus.REJECTED,
                        error_message="paper broker fills market orders only",
                        submitted_at=now,
                        side=order.side,
                    ),
                    [
                        (
                            OrderStatus.SUBMITTED,
                            OrderStatus.REJECTED,
                            REASON_UNSUPPORTED_ORDER_TYPE,
                            now,
                        )
                    ],
                    [],
                )
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

            ask_offset = self._spread if order.side == OrderSide.BUY else 0.0
            fill_price = self._apply_slippage(base_price + ask_offset, order.side)
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

    # True when no fill can follow. Paper is the only filler of its orders, so an id that
    # is not resting (filled, refused, dropped on unload or from an earlier process) is as
    # good as cancelled. The caller asked for the cancel, so no order callback goes out.
    async def cancel_order(self, broker_order_id: str) -> bool:
        async with self._lock:
            resting = self._resting.pop(broker_order_id, None)
        if resting is None:
            return True
        await self._emit_event(
            str(resting[0].id), OrderStatus.SUBMITTED, OrderStatus.CANCELLED, REASON_CANCELLED
        )
        return True

    # Closes at the last bar close, plus the spread for a BUY.
    async def close_position(
        self, subscription_id: str, symbol: str, *, reason: str, deadline: datetime | None = None
    ) -> bool:
        pos = self._positions.get(f"{subscription_id}:{symbol}")
        if pos is None or pos.is_closed:
            return False
        side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
        trigger = self._current_prices.get(symbol.upper(), pos.current_price)
        if side == OrderSide.BUY:
            trigger += self._spread
        return await self._fire_synthetic_exit(pos, trigger, side, reason)

    # Used on unload, when no one is left to manage the position. Opening a paper position
    # moves no cash, so the balance stays as it is.
    def drop_positions(self, subscription_id: str) -> int:
        keys = [k for k, p in self._positions.items() if p.subscription_id == subscription_id]
        for key in keys:
            del self._positions[key]
        self._resting = {
            k: v for k, v in self._resting.items() if v[0].subscription_id != subscription_id
        }
        return len(keys)

    # Copies, because the mirror reduces its own row on an exit fill.
    # A takeover restores no stop: the strategy re-places it on its next bar.
    def restore(self, positions: list[PositionAggregate], realized_net: float) -> None:
        self._positions.clear()
        self._resting.clear()
        entry_commissions = 0.0
        for row in positions:
            commission = self._commission(row.entry_price, row.quantity)
            entry_commissions += commission
            self._positions[f"{row.subscription_id}:{row.symbol}"] = row.model_copy(
                deep=True, update={"entry_commission": commission}
            )
        self._balance = self._initial_balance + realized_net - entry_commissions

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
        return list(self._order_events.get(order_id, []))

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        self._order_callbacks.clear()

    async def subscribe_trades(self, callback: TradeCallback) -> None:
        self._trade_callbacks.append(callback)

    async def unsubscribe_trades(self) -> None:
        self._trade_callbacks.clear()

    async def subscribe_order_event(self, callback: OrderEventCallback) -> None:
        self._event_callbacks.append(callback)

    async def unsubscribe_order_event(self) -> None:
        self._event_callbacks.clear()

    def has_price(self, symbol: str) -> bool:
        return symbol.upper() in self._current_prices

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
        # Price-unit notional on purpose: the shipped margin model, not contract value.
        return fill_price * order.quantity + commission <= self._balance

    # Call under lock. Futures/margin model: opening moves no cash; balance moves by the
    # realized-pnl delta on a reduce. reduce_quantity accumulates position.realized_pnl, so
    # crediting the cumulative value would multi-count partial closes.
    def _execute_fill(
        self, order: OrderAggregate, fill_price: float, commission: float
    ) -> list[TradeClosedEvent]:
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
            multiplier=self._contract_spec.multiplier,
        )

    # Call under lock. The single debit point for every fill path, so none can skip
    # commission. Computed before the fill so it is threaded in as entry or exit cost.
    def _execute_fill_with_commission(
        self, order: OrderAggregate, fill_price: float
    ) -> tuple[float, list[TradeClosedEvent]]:
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

    # when defaults to simulation time so backtest events carry the replay timestamp.
    async def _emit_event(
        self,
        order_id: str,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        reason: str,
        when: datetime | None = None,
    ) -> None:
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

    # Only bars of the finest interval seen for the symbol act: a coarser bar's range starts
    # before entries made inside it.
    def _is_finest(self, event: BarCompletedEvent) -> bool:
        secs = INTERVAL_SECONDS[event.interval]
        finest = min(secs, self._finest_interval_s.get(event.symbol, secs))
        self._finest_interval_s[event.symbol] = finest
        return secs <= finest

    # Call under lock. Only positions that existed when the bar was published act, so a
    # position opened on the signal bar is checked from the next bar.
    def _sl_tp_hits(self, event: BarCompletedEvent, skip: set) -> list[_Exit]:
        hits: list[_Exit] = []
        for pos in self._positions.values():
            if pos.is_closed or pos.symbol != event.symbol or pos.id in skip:
                continue
            if pos.opened_at >= event.occurred_at:
                continue
            if pos.sl_price is None and pos.tp_price is None:
                continue
            hit = self._check_sl_tp(pos, event)
            if hit is not None:
                hits.append((pos, hit[0], hit[1], hit[2]))
        return hits

    # The engine calls this before any strategy decides on the bar: the broker's own bar
    # handler runs after the strategies, so a stop re-placed every bar would be cancelled
    # before that handler saw a touching bar. A stop fills on a later bar only, and only
    # for a running subscription. The fill repeats the placement checks as a last guard:
    # one position per subscription and the balance. BUY fills at max(ask open, stop), SELL
    # at min(open, stop), which is optimistic in a fast market. On the fill bar only the SL
    # is checked; the TP waits for the next bar.
    async def fill_resting_stops(self, event: BarCompletedEvent, running: set[str]) -> None:
        if not self._is_finest(event):
            return
        # An EXIT on this bar closes at its close.
        self._current_prices[event.symbol.upper()] = event.close
        now = get_current_time()
        fills: list[tuple[OrderResult, list[TradeClosedEvent]]] = []
        refused: list[tuple[OrderAggregate, str, str]] = []
        to_close: list[_Exit] = []
        async with self._lock:
            filled: set = set()
            for broker_order_id, (order, placed_at) in list(self._resting.items()):
                if order.symbol != event.symbol or placed_at >= event.occurred_at:
                    continue
                stop = order.stop_price or 0.0
                if order.side == OrderSide.BUY:
                    if event.high + self._spread < stop:
                        continue
                    trigger = max(event.open + self._spread, stop)
                else:
                    if event.low > stop:
                        continue
                    trigger = min(event.open, stop)
                if order.subscription_id not in running:
                    continue
                price = self._apply_slippage(trigger, order.side)
                key = f"{order.subscription_id}:{order.symbol}"
                held = self._positions.get(key)
                del self._resting[broker_order_id]
                if held is not None and not held.is_closed:
                    refused.append((order, broker_order_id, "position open"))
                    continue
                if not self._can_afford(order, price):
                    refused.append((order, broker_order_id, "Insufficient balance"))
                    continue
                commission, trades = self._execute_fill_with_commission(order, price)
                pos = self._positions[key]
                filled.add(pos.id)
                fills.append(
                    (
                        OrderResult(
                            order_id=str(order.id),
                            broker_order_id=broker_order_id,
                            status=OrderStatus.FILLED,
                            filled_quantity=order.quantity,
                            filled_price=price,
                            submitted_at=placed_at,
                            sl_price=order.sl_price,
                            tp_price=order.tp_price,
                            side=order.side,
                            commission=commission,
                        ),
                        trades,
                    )
                )
                # An SL already past the fill exits at the fill, never at a better price
                # than the bar traded.
                sl = pos.sl_price
                if sl is None:
                    continue
                if pos.side == PositionSide.LONG and event.low <= sl:
                    to_close.append((pos, min(sl, price), OrderSide.SELL, REASON_AUTO_SL))
                elif pos.side == PositionSide.SHORT and event.high + self._spread >= sl:
                    to_close.append(
                        (pos, max(sl, price + self._spread), OrderSide.BUY, REASON_AUTO_SL)
                    )
            to_close.extend(self._sl_tp_hits(event, filled))

        # Every outcome is dispatched even when a subscriber raises: the fills above are
        # already applied, and one that never reaches the order service blocks its next entry.
        # The first error is raised at the end. No OrderFilledEvent for a stop fill: the order
        # service publishes it from the FILLED callback.
        errors: list[Exception] = []
        for result, trades in fills:
            try:
                await self._emit_event(
                    result.order_id,
                    OrderStatus.SUBMITTED,
                    OrderStatus.FILLED,
                    REASON_STOP_FILL,
                    now,
                )
                await self._notify_callbacks(result)
                for trade in trades:
                    await self._notify_trade_callbacks(trade)
            except Exception as e:
                errors.append(e)
        for order, broker_order_id, message in refused:
            logger.warning(
                "paper.stop_refused",
                order_id=str(order.id),
                subscription_id=order.subscription_id,
                reason=message,
            )
            try:
                await self._emit_event(
                    str(order.id),
                    OrderStatus.SUBMITTED,
                    OrderStatus.CANCELLED,
                    REASON_CANCELLED,
                    now,
                )
                await self._notify_callbacks(
                    OrderResult(
                        order_id=str(order.id),
                        broker_order_id=broker_order_id,
                        status=OrderStatus.CANCELLED,
                        error_message=message,
                        submitted_at=now,
                        side=order.side,
                    )
                )
            except Exception as e:
                errors.append(e)
        for pos, exit_price, exit_side, reason in to_close:
            try:
                await self._fire_synthetic_exit(pos, exit_price, exit_side, reason)
            except Exception as e:
                errors.append(e)
        if errors:
            raise errors[0]

    # A level the bar opens past fills at the open; when SL and TP both hit inside one bar,
    # SL fills first (worst case).
    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        if not self._is_finest(event):
            return
        self._current_prices[event.symbol.upper()] = event.close
        # After the engine's pre-strategy pass this finds nothing new on the bar; it still
        # acts while the engine skips that pass (a drain or a lapsed lease).
        async with self._lock:
            to_close = self._sl_tp_hits(event, set())

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

    def _check_sl_tp(
        self, pos: PositionAggregate, bar: BarCompletedEvent
    ) -> tuple[float, OrderSide, str] | None:
        # The open is the bar's first trade: a level it is already past fills there.
        # Inside the bar, SL is checked before TP so SL wins when both are crossed.
        sl, tp = pos.sl_price, pos.tp_price
        if pos.side == PositionSide.LONG:
            if tp is not None and bar.open >= tp:
                return (bar.open, OrderSide.SELL, REASON_AUTO_TP)
            if sl is not None and bar.low <= sl:
                return (min(bar.open, sl), OrderSide.SELL, REASON_AUTO_SL)
            if tp is not None and bar.high >= tp:
                return (tp, OrderSide.SELL, REASON_AUTO_TP)
        else:  # SHORT exits buy at the ask
            ask_open = bar.open + self._spread
            if tp is not None and ask_open <= tp:
                return (ask_open, OrderSide.BUY, REASON_AUTO_TP)
            if sl is not None and bar.high + self._spread >= sl:
                return (max(ask_open, sl), OrderSide.BUY, REASON_AUTO_SL)
            if tp is not None and bar.low + self._spread <= tp:
                return (tp, OrderSide.BUY, REASON_AUTO_TP)
        return None

    async def _fire_synthetic_exit(
        self,
        pos: PositionAggregate,
        trigger_price: float,
        exit_side: OrderSide,
        reason: str,
    ) -> bool:
        fill_price = self._apply_slippage(trigger_price, exit_side)
        broker_order_id = generate_id_str()
        now = get_current_time()
        async with self._lock:
            # An earlier exit's callbacks may have awaited while this subscription was
            # unloaded, and a fill for its dropped position would open a new one. A second
            # exit of one position must never reverse it; closed is decided by state, not
            # by identity.
            if (
                self._positions.get(f"{pos.subscription_id}:{pos.symbol}") is not pos
                or pos.is_closed
                or pos.quantity <= 0
            ):
                return False
            exit_order = OrderAggregate.create(
                subscription_id=pos.subscription_id,
                symbol=pos.symbol,
                side=exit_side,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                price=trigger_price,
            )
            commission, trades = self._execute_fill_with_commission(exit_order, fill_price)
            trades = [replace(t, exit_reason=reason) for t in trades]
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
        return True

    def reset(self) -> None:
        self._balance = self._initial_balance
        self._positions.clear()
        self._current_prices.clear()
        self._order_events.clear()
        self._finest_interval_s.clear()
        self._resting.clear()
