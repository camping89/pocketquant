"""Position tracker - manages per-strategy position state."""

import asyncio

import structlog

from src.common.messaging import EventBus
from src.domain.order import OrderFilled, OrderSide
from src.domain.position import PositionAggregate, PositionOpened, PositionSide
from src.features.trading.repositories import PositionRepository

logger = structlog.get_logger(__name__)


class PositionTracker:
    """Tracks positions per strategy with P&L calculation.

    Subscribes to OrderFilled events to update positions automatically.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._positions: dict[str, PositionAggregate] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Subscribe to order events and load open positions."""
        await self.load_open_positions()
        self._event_bus.subscribe(OrderFilled, self._on_order_filled)
        logger.info("position_tracker_started")

    async def load_open_positions(self) -> None:
        """Load open positions from database on startup."""
        positions = await PositionRepository.find_open()
        async with self._lock:
            for pos in positions:
                self._positions[pos.strategy_id] = pos
        logger.info("loaded_open_positions", count=len(positions))

    async def stop(self) -> None:
        """Unsubscribe from events."""
        logger.info("position_tracker_stopped")

    async def _on_order_filled(self, event: OrderFilled) -> None:
        """Handle order fill by updating position."""
        async with self._lock:
            position = self._positions.get(event.strategy_id)

            if position is None:
                # New position
                side = (
                    PositionSide.LONG
                    if event.side == OrderSide.BUY
                    else PositionSide.SHORT
                )

                position = PositionAggregate.open(
                    strategy_id=event.strategy_id,
                    symbol=event.symbol,
                    exchange=event.exchange,
                    side=side,
                    entry_price=event.filled_price,
                    quantity=event.filled_quantity,
                )

                self._positions[event.strategy_id] = position

                # Persist new position
                await PositionRepository.save(position)

                await self._event_bus.publish(
                    PositionOpened(
                        position_id=position.id,
                        strategy_id=event.strategy_id,
                        symbol=event.symbol,
                        exchange=event.exchange,
                        side=side,
                        entry_price=event.filled_price,
                        quantity=event.filled_quantity,
                    )
                )

                logger.info(
                    "position_opened",
                    strategy_id=event.strategy_id,
                    symbol=event.symbol,
                    side=side.value,
                    entry_price=event.filled_price,
                )

            else:
                # Update existing position
                is_same_side = (
                    event.side == OrderSide.BUY
                    and position.side == PositionSide.LONG
                ) or (
                    event.side == OrderSide.SELL
                    and position.side == PositionSide.SHORT
                )

                if is_same_side:
                    # Adding to position
                    position.add_quantity(event.filled_quantity, event.filled_price)

                    # Persist updated position
                    await PositionRepository.save(position)

                    logger.info(
                        "position_increased",
                        strategy_id=event.strategy_id,
                        quantity=position.quantity,
                    )
                else:
                    # Reducing position
                    position.reduce_quantity(event.filled_quantity, event.filled_price)

                    # Persist updated/closed position
                    await PositionRepository.save(position)

                    if position.is_closed:
                        # Position fully closed
                        del self._positions[event.strategy_id]

                        logger.info(
                            "position_closed",
                            strategy_id=event.strategy_id,
                            realized_pnl=position.realized_pnl,
                        )
                    else:
                        logger.info(
                            "position_reduced",
                            strategy_id=event.strategy_id,
                            remaining=position.quantity,
                            realized_pnl=position.realized_pnl,
                        )

    def get(self, strategy_id: str) -> PositionAggregate | None:
        """Get position for a strategy."""
        return self._positions.get(strategy_id)

    def get_all(self) -> list[PositionAggregate]:
        """Get all open positions."""
        return [p for p in self._positions.values() if not p.is_closed]

    def get_position_summary(self, strategy_id: str) -> dict | None:
        """Get position summary with P&L."""
        position = self._positions.get(strategy_id)
        if not position:
            return None

        return {
            "id": position.id,
            "strategy_id": position.strategy_id,
            "symbol": position.symbol,
            "exchange": position.exchange,
            "side": position.side.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "unrealized_pnl": position.unrealized_pnl,
            "realized_pnl": position.realized_pnl,
            "is_closed": position.is_closed,
        }

    def get_all_summaries(self) -> list[dict]:
        """Get all position summaries."""
        return [
            self.get_position_summary(sid)
            for sid in self._positions.keys()
            if self.get_position_summary(sid)
        ]

    async def update_price(self, strategy_id: str, price: float) -> None:
        """Update current price for a position."""
        async with self._lock:
            position = self._positions.get(strategy_id)
            if position and not position.is_closed:
                position.update_price(price)
                # Note: Price updates are frequent, don't persist every update
                # Persistence happens on quantity changes

    async def get_async(self, strategy_id: str) -> PositionAggregate | None:
        """Get position from memory or database."""
        position = self._positions.get(strategy_id)
        if position:
            return position
        return await PositionRepository.get_by_strategy(strategy_id)
