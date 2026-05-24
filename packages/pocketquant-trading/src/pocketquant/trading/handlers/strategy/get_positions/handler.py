"""GetStrategyPositionsHandler — list open positions for a strategy instance."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.get_positions.query import (
    GetStrategyPositionsQuery,
)
from pocketquant.trading.persistence.position_repository import PositionRepository


@handles(GetStrategyPositionsQuery)
class GetStrategyPositionsHandler(Handler[GetStrategyPositionsQuery, list[dict]]):
    """Return open positions (0 or more) as FE-friendly dicts."""

    def __init__(self, position_repository: PositionRepository) -> None:
        self._position_repo = position_repository

    async def handle(self, request: GetStrategyPositionsQuery) -> list[dict]:
        positions = await self._position_repo.find_open_by_strategy(request.strategy_id)
        return [
            {
                "symbol": p.symbol,
                "direction": p.side.value.upper(),
                "entry_price": p.entry_price,
                "quantity": p.quantity,
                "unrealized_pnl": p.unrealized_pnl,
                "entry_time": p.opened_at.isoformat(),
                "sl_price": p.sl_price,
                "tp_price": p.tp_price,
            }
            for p in positions
        ]
