"""GetSubscriptionBacktestHandler — return raw cached backtest doc or 404."""

from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.get_subscription_backtest.query import (
    GetSubscriptionBacktestQuery,
)


@handles(GetSubscriptionBacktestQuery)
class GetSubscriptionBacktestHandler(Handler[GetSubscriptionBacktestQuery, dict]):
    """Handle GetSubscriptionBacktestQuery — return raw doc (status may be any value).

    Returns the full document including status, metrics, equity_curve, trades etc.
    Uses find_doc_by_subscription() rather than find_by_subscription() so that
    status-only docs ('running', 'failed') that lack full BacktestResult fields
    are returned cleanly without deserialisation errors.
    404 is raised only when no document exists at all (backtest never triggered).
    """

    def __init__(self, backtest_repository: BacktestRepository) -> None:
        self._bt_repo = backtest_repository

    async def handle(self, request: GetSubscriptionBacktestQuery) -> dict:
        """Return the backtest doc for the subscription, or 404 if never run."""
        doc = await self._bt_repo.find_doc_by_subscription(request.sub_id)
        if doc is None:
            raise NotFoundError(
                f"No backtest found for subscription '{request.sub_id}'. "
                "Trigger a run via POST /strategies/{strategy_code}/run-all-backtests first."
            )
        return doc
