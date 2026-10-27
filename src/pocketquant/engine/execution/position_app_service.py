import asyncio

import structlog

from pocketquant.core.common.messaging import EventBus, event_handler, get_event_registry
from pocketquant.core.domain.order import OrderFilledEvent, OrderSide
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

logger = structlog.get_logger(__name__)


class PositionAppService:
    def __init__(
        self,
        event_bus: EventBus,
        position_repository: PositionRepository,
        symbol_lookup: SymbolLookupHelper | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._position_repo = position_repository
        # The persisted mirror reports PnL to the UI, so it needs the same contract
        # multiplier as the broker; without a lookup every position is linear.
        self._symbol_lookup = symbol_lookup
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

    @event_handler(OrderFilledEvent)
    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        async with self._lock:
            position = self._positions.get(event.subscription_id)

            if position is None:
                side = PositionSide.LONG if event.side == OrderSide.BUY else PositionSide.SHORT
                multiplier = (
                    (await self._symbol_lookup.contract_spec(event.symbol)).multiplier
                    if self._symbol_lookup
                    else 1.0
                )

                position = PositionAggregate.open(
                    subscription_id=event.subscription_id,
                    symbol=event.symbol,
                    side=side,
                    entry_price=event.filled_price,
                    quantity=event.filled_quantity,
                    multiplier=multiplier,
                )

                self._positions[event.subscription_id] = position

                await self._position_repo.save(position)

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

        # Note: Price updates are frequent, don't persist every update
        # Persistence happens on quantity changes
