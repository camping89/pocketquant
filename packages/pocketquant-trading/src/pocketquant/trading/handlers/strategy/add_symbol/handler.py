"""AddSymbolHandler — persist a new StrategySubscription for a loaded strategy."""

from datetime import UTC, datetime

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.domain.subscription import StrategySubscription
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)


@handles(AddSymbolCommand)
class AddSymbolHandler(Handler[AddSymbolCommand, dict]):
    """Handle AddSymbolCommand — auto-load template if needed, then persist subscription."""

    def __init__(
        self,
        strategy_app_service: StrategyAppService,
        strategy_subscription_repository: StrategySubscriptionRepository,
        tracked_symbol_repository: TrackedSymbolRepository,
    ) -> None:
        self._strategy_service = strategy_app_service
        self._sub_repo = strategy_subscription_repository
        self._tracked_repo = tracked_symbol_repository

    async def handle(self, request: AddSymbolCommand) -> dict:
        """Validate strategy is in memory and symbol is tracked, then persist subscription.

        If ``request.strategy_id`` matches a template in ``STRATEGY_REGISTRY`` but is not
        yet loaded, this auto-loads it with the request's (symbol, interval) as defaults.

        ``request.symbol`` must be composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
        """
        symbol = request.symbol.upper()
        if not await self._tracked_repo.exists(symbol):
            raise NotFoundError(
                f"Symbol '{symbol}' is not tracked. "
                "Admin must add it to tracked_symbols first.",
                error_code="SYMBOL_NOT_TRACKED",
            )

        if self._strategy_service.get_strategy(request.strategy_id) is None:
            strategy_class = STRATEGY_REGISTRY.get(request.strategy_id)
            if strategy_class is None:
                raise NotFoundError(
                    f"Strategy '{request.strategy_id}' is not loaded "
                    "and no template matches in the registry."
                )
            await self._strategy_service.load_strategy(
                StrategyConfig(
                    id=request.strategy_id,
                    name=request.strategy_id,
                    symbol=symbol,
                    interval=request.interval,
                ),
                strategy_class=strategy_class,
            )

        sub_id = StrategySubscription.deterministic_id(
            request.strategy_id, symbol, request.interval
        )
        sub = StrategySubscription(
            id=sub_id,
            strategy_id=request.strategy_id,
            symbol=symbol,
            interval=Interval(request.interval),
            created_at=datetime.now(UTC),
        )
        await self._sub_repo.add(sub)
        return {
            "id": sub.id,
            "strategy_id": sub.strategy_id,
            "symbol": sub.symbol,
            "interval": sub.interval.value,
            "created_at": sub.created_at.isoformat(),
        }
