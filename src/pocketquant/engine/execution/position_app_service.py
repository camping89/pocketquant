import asyncio

import structlog

from pocketquant.core.common.messaging import EventBus, event_handler, get_event_registry
from pocketquant.core.domain.order import OrderFilledEvent, OrderSide
from pocketquant.core.domain.position import PositionAggregate, PositionOpenedEvent, PositionSide
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)

logger = structlog.get_logger(__name__)


class PositionAppService:
    def __init__(self, event_bus: EventBus, position_repository: PositionRepository) -> None:
        self._event_bus = event_bus
        self._position_repo = position_repository
        self._positions: dict[str, PositionAggregate] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self.load_open_positions()
        registry = get_event_registry()
        registry.register_instance(self, self._event_bus)
        logger.info("position_tracker_started")

    async def load_open_positions(self) -> None:
        positions = await self._position_repo.find_open()
        async with self._lock:
            for pos in positions:
                self._positions[pos.subscription_id] = pos
        logger.info("loaded_open_positions", count=len(positions))

    async def stop(self) -> None:
        logger.info("position_tracker_stopped")

    @event_handler(OrderFilledEvent)
    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        async with self._lock:
            position = self._positions.get(event.subscription_id)

            if position is None:
                side = PositionSide.LONG if event.side == OrderSide.BUY else PositionSide.SHORT

                position = PositionAggregate.open(
                    subscription_id=event.subscription_id,
                    symbol=event.symbol,
                    side=side,
                    entry_price=event.filled_price,
                    quantity=event.filled_quantity,
                )

                self._positions[event.subscription_id] = position

                await self._position_repo.save(position)

                await self._event_bus.publish(
                    PositionOpenedEvent(
                        position_id=str(position.id),
                        subscription_id=event.subscription_id,
                        symbol=event.symbol,
                        side=side,
                        entry_price=event.filled_price,
                        quantity=event.filled_quantity,
                    )
                )

                logger.info(
                    "position_opened",
                    subscription_id=event.subscription_id,
                    symbol=event.symbol,
                    side=side.value,
                    entry_price=event.filled_price,
                )

            else:
                is_same_side = (
                    event.side == OrderSide.BUY and position.side == PositionSide.LONG
                ) or (event.side == OrderSide.SELL and position.side == PositionSide.SHORT)

                if is_same_side:
                    position.add_quantity(event.filled_quantity, event.filled_price)

                    await self._position_repo.save(position)

                    logger.info(
                        "position_increased",
                        subscription_id=event.subscription_id,
                        quantity=position.quantity,
                    )
                else:
                    position.reduce_quantity(event.filled_quantity, event.filled_price)

                    await self._position_repo.save(position)

                    if position.is_closed:
                        del self._positions[event.subscription_id]

                        logger.info(
                            "position_closed",
                            subscription_id=event.subscription_id,
                            realized_pnl=position.realized_pnl,
                        )
                    else:
                        logger.info(
                            "position_reduced",
                            subscription_id=event.subscription_id,
                            remaining=position.quantity,
                            realized_pnl=position.realized_pnl,
                        )

    def get(self, strategy_id: str) -> PositionAggregate | None:
        return self._positions.get(strategy_id)

    def get_all(self) -> list[PositionAggregate]:
        return [p for p in self._positions.values() if not p.is_closed]

    def get_position_summary(self, strategy_id: str) -> dict | None:
        position = self._positions.get(strategy_id)
        if not position:
            return None

        return {
            "id": str(position.id),
            "subscription_id": position.subscription_id,
            "symbol": position.symbol,
            "side": position.side.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "unrealized_pnl": position.unrealized_pnl,
            "realized_pnl": position.realized_pnl,
            "is_closed": position.is_closed,
        }

    def get_all_summaries(self) -> list[dict]:
        summaries = []
        for sid in self._positions.keys():
            summary = self.get_position_summary(sid)
            if summary:
                summaries.append(summary)
        return summaries

    async def update_price(self, strategy_id: str, price: float) -> None:
        async with self._lock:
            position = self._positions.get(strategy_id)
            if position and not position.is_closed:
                position.update_price(price)
                # Note: Price updates are frequent, don't persist every update
                # Persistence happens on quantity changes

    async def get_async(self, strategy_id: str) -> PositionAggregate | None:
        position = self._positions.get(strategy_id)
        if position:
            return position
        return await self._position_repo.get_by_subscription(strategy_id)
