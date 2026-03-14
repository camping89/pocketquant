"""Paper broker implementation for simulated trading."""

import asyncio
from datetime import UTC, datetime

from src.common.uuid import generate_id_str
from src.domain.order import OrderAggregate, OrderSide, OrderStatus
from src.domain.position import PositionAggregate, PositionSide
from src.infrastructure.brokers.interface import IBroker, OrderCallback
from src.infrastructure.brokers.models import AccountBalance, OrderResult


class PaperBroker(IBroker):
    """Simulated broker for paper trading and backtesting.

    Features:
    - Configurable slippage simulation
    - Fill delay simulation
    - In-memory position tracking
    - Order callback subscription
    """

    def __init__(
        self,
        initial_balance: float = 100_000.0,
        slippage_percent: float = 0.001,  # 0.1% default
        fill_delay_ms: int = 50,
        currency: str = "USDT",
    ) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._slippage = slippage_percent
        self._fill_delay = fill_delay_ms
        self._currency = currency

        self._positions: dict[str, PositionAggregate] = {}
        self._orders: dict[str, OrderAggregate] = {}
        self._order_callbacks: list[OrderCallback] = []
        self._lock = asyncio.Lock()
        self._connected = False
        # Current market prices for each symbol (used in backtesting)
        self._current_prices: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "paper"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def slippage(self) -> float:
        """Get current slippage percentage."""
        return self._slippage

    @slippage.setter
    def slippage(self, value: float) -> None:
        """Set slippage percentage."""
        self._slippage = value

    async def connect(self) -> None:
        """Paper broker is always ready."""
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect paper broker."""
        self._connected = False

    async def submit_order(self, order: OrderAggregate) -> OrderResult:
        """Simulate order execution with slippage."""
        async with self._lock:
            # Simulate network delay
            if self._fill_delay > 0:
                await asyncio.sleep(self._fill_delay / 1000)

            # Get execution price with slippage
            base_price = order.price if order.price else self._get_market_price(order)
            fill_price = self._apply_slippage(base_price, order.side)

            # Check if we have enough balance
            order_value = fill_price * order.quantity
            if order.side == OrderSide.BUY and order_value > self._balance:
                return OrderResult(
                    order_id=order.id,
                    broker_order_id=generate_id_str(),
                    status=OrderStatus.REJECTED,
                    error_message="Insufficient balance",
                )

            # Execute the fill
            broker_order_id = generate_id_str()
            self._execute_fill(order, fill_price)
            self._orders[order.id] = order

            result = OrderResult(
                order_id=order.id,
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                filled_price=fill_price,
                submitted_at=datetime.now(UTC),
            )

            # Notify subscribers
            await self._notify_callbacks(result)

            return result

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel is always successful for filled orders (no-op)."""
        # Paper broker fills immediately, so cancellation is a no-op
        return True

    async def get_positions(self) -> list[PositionAggregate]:
        """Get all open positions."""
        async with self._lock:
            return [p for p in self._positions.values() if not p.is_closed]

    async def get_balance(self) -> AccountBalance:
        """Get current account balance."""
        async with self._lock:
            unrealized = sum(p.unrealized_pnl for p in self._positions.values() if not p.is_closed)
            return AccountBalance(
                total_equity=self._balance + unrealized,
                available_balance=self._balance,
                currency=self._currency,
                unrealized_pnl=unrealized,
            )

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        """Add order update callback."""
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        """Clear all order callbacks."""
        self._order_callbacks.clear()

    def set_current_price(self, symbol: str, price: float) -> None:
        """Set current market price for a symbol (used in backtesting).

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").
            price: Current market price (typically bar close).
        """
        self._current_prices[symbol.upper()] = price

    def _get_market_price(self, order: OrderAggregate) -> float:
        """Get simulated market price for order.

        For market orders, use the last known price for the symbol,
        or require price to be set explicitly.
        """
        if order.price:
            return order.price

        # Check tracked prices first (set by backtest runner)
        symbol_upper = order.symbol.upper()
        if symbol_upper in self._current_prices:
            return self._current_prices[symbol_upper]

        # Check if we have a position with current price
        position_key = f"{order.strategy_id}:{order.symbol}"
        if position_key in self._positions:
            pos = self._positions[position_key]
            if pos.current_price > 0:
                return pos.current_price

        # No price available - this shouldn't happen in normal flow
        # The StrategyAppService should always provide price context
        raise ValueError(
            f"No market price available for {order.symbol}. "
            "Market orders require price context from strategy signal."
        )

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        """Apply slippage to price based on order side."""
        if side == OrderSide.BUY:
            # Buying: price goes up
            return price * (1 + self._slippage)
        else:
            # Selling: price goes down
            return price * (1 - self._slippage)

    def _execute_fill(self, order: OrderAggregate, fill_price: float) -> None:
        """Update balance and positions based on fill."""
        position_key = f"{order.strategy_id}:{order.symbol}"
        order_value = fill_price * order.quantity

        if order.side == OrderSide.BUY:
            # Deduct from balance
            self._balance -= order_value

            # Update or create position
            if position_key in self._positions:
                pos = self._positions[position_key]
                if pos.side == PositionSide.LONG:
                    pos.add_quantity(order.quantity, fill_price)
                else:
                    # Closing short position
                    pos.reduce_quantity(order.quantity, fill_price)
                    self._balance += pos.realized_pnl
            else:
                self._positions[position_key] = PositionAggregate.open(
                    strategy_id=order.strategy_id,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    side=PositionSide.LONG,
                    entry_price=fill_price,
                    quantity=order.quantity,
                )
        else:  # SELL
            # Add to balance
            self._balance += order_value

            if position_key in self._positions:
                pos = self._positions[position_key]
                if pos.side == PositionSide.LONG:
                    # Closing long position
                    pos.reduce_quantity(order.quantity, fill_price)
                    self._balance += pos.realized_pnl
                else:
                    # Adding to short
                    pos.add_quantity(order.quantity, fill_price)
            else:
                self._positions[position_key] = PositionAggregate.open(
                    strategy_id=order.strategy_id,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    side=PositionSide.SHORT,
                    entry_price=fill_price,
                    quantity=order.quantity,
                )

    async def _notify_callbacks(self, result: OrderResult) -> None:
        """Notify all registered callbacks of order update.

        NOTE: Callback errors are re-raised after logging. If callbacks must not
        break the broker, the caller should handle exceptions appropriately.
        """
        errors: list[Exception] = []
        for callback in self._order_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                # Collect errors but continue notifying other callbacks
                errors.append(e)

        if errors:
            # NOTE: Re-raising first error after all callbacks attempted.
            # This ensures all callbacks get notified while still surfacing failures.
            raise errors[0]

    def reset(self) -> None:
        """Reset broker to initial state (for backtesting)."""
        self._balance = self._initial_balance
        self._positions.clear()
        self._orders.clear()
        self._current_prices.clear()
