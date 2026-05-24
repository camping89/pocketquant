"""Query: list completed trades (closed positions) for a strategy instance."""

from pydantic import BaseModel


class GetStrategyTradesQuery(BaseModel):
    """Read-side query — returns the N most-recent closed positions for ``strategy_id``.

    Closed positions are the canonical 'completed trade' record (entry + exit
    + realized PnL). Returning them avoids pairing raw fills client-side.
    """

    strategy_id: str
    limit: int = 100
