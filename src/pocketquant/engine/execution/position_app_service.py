import asyncio

import structlog

from pocketquant.core.common.messaging import EventBus
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

    async def start(self, paper_subscription_ids: frozenset[str] = frozenset()) -> None:
        await self.load_open_positions(paper_subscription_ids)
        self._event_bus.subscribe(OrderFilledEvent, self._on_order_filled)
        logger.info("position_tracker_started")

    async def load_open_positions(self, paper_subscription_ids: frozenset[str]) -> None:
        """Load the open rows; delete the rows of paper subscriptions.

        A paper broker keeps positions in memory, so a restart loses them. Their
        rows are deleted, not closed: a closed row reads as a completed trade.
        Every other row stays open, because a venue may still hold it and the
        venue snapshot maps its positions to these rows.
        """
        positions = await self._position_repo.find_open()
        kept = [p for p in positions if p.subscription_id not in paper_subscription_ids]
        for sid in {p.subscription_id for p in positions} & paper_subscription_ids:
            await self._position_repo.delete_open_by_subscription(sid)
        async with self._lock:
            for pos in kept:
                self._positions[pos.subscription_id] = pos
        logger.info(
            "loaded_open_positions", count=len(kept), paper_dropped=len(positions) - len(kept)
        )

    async def drop(self, subscription_id: str) -> None:
        """Forget a paper subscription's open position, in memory and in Mongo."""
        async with self._lock:
            self._positions.pop(subscription_id, None)
            await self._position_repo.delete_open_by_subscription(subscription_id)

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
                    sl_price=event.sl_price,
                    tp_price=event.tp_price,
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
