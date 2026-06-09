"""GetStrategyTradesHandler — list closed positions mapped to StrategyTrade shape."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.trading.handlers.strategy.get_trades.query import (
    GetStrategyTradesQuery,
)


@handles(GetStrategyTradesQuery)
class GetStrategyTradesHandler(Handler[GetStrategyTradesQuery, list[dict]]):
    """Return closed positions as the FE-consumed StrategyTrade shape."""

    def __init__(self, position_repository: PositionRepository) -> None:
        self._position_repo = position_repository

    async def handle(self, request: GetStrategyTradesQuery) -> list[dict]:
        closed = await self._position_repo.find_closed_by_subscription(
            request.subscription_id, limit=request.limit
        )
        return [
            {
                "id": p.id,
                "direction": p.side.value.upper(),
                "entry_price": p.entry_price,
                # Position close sets current_price = exit_price.
                "exit_price": p.current_price,
                "entry_time": p.opened_at.isoformat(),
                "exit_time": p.closed_at.isoformat() if p.closed_at else None,
                "pnl": p.realized_pnl,
                "quantity": p.quantity,
            }
            for p in closed
        ]
