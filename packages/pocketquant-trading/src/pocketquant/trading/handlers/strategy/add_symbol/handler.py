"""AddSymbolHandler — persist a new Subscription for a loaded strategy template."""

from datetime import UTC, datetime

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.core.domain.subscription import Subscription
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


@handles(AddSymbolCommand)
class AddSymbolHandler(Handler[AddSymbolCommand, dict]):
    """Handle AddSymbolCommand — auto-load template if needed, then persist subscription."""

    def __init__(
        self,
        strategy_app_service: StrategyAppService,
        subscription_repository: SubscriptionRepository,
        tracked_symbol_repository: TrackedSymbolRepository,
    ) -> None:
        self._strategy_service = strategy_app_service
        self._sub_repo = subscription_repository
        self._tracked_repo = tracked_symbol_repository

    async def handle(self, request: AddSymbolCommand) -> dict:
        """Persist subscription and load a dedicated strategy instance.

        Each subscription owns its own ``IStrategy`` instance keyed by ``sub.id``
        so that subscribing the same template to multiple (symbol, interval)
        pairs results in independent runtime instances. ``request.strategy_id``
        is the template code (matched against ``STRATEGY_REGISTRY``).

        ``request.symbol`` must be composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
        """
        symbol = request.symbol.upper()
        if not await self._tracked_repo.exists(symbol):
            raise NotFoundError(
                f"Symbol '{symbol}' is not tracked. Admin must add it to tracked_symbols first.",
                error_code="SYMBOL_NOT_TRACKED",
            )

        strategy_class = STRATEGY_REGISTRY.get(request.strategy_id)
        if strategy_class is None:
            raise NotFoundError(f"Strategy template '{request.strategy_id}' not found in registry.")

        sub_id = Subscription.deterministic_id(request.strategy_id, symbol, request.interval)

        if self._strategy_service.get_strategy(sub_id) is None:
            await self._strategy_service.load_strategy(
                StrategyConfig(
                    id=sub_id,
                    name=request.strategy_id,
                    symbol=symbol,
                    interval=request.interval,
                ),
                strategy_class=strategy_class,
            )

        sub = Subscription(
            id=sub_id,
            strategy_code=request.strategy_id,
            symbol=symbol,
            interval=Interval(request.interval),
            created_at=datetime.now(UTC),
        )
        await self._sub_repo.add(sub)
        return {
            "id": sub.id,
            "strategy_code": sub.strategy_code,
            "symbol": sub.symbol,
            "interval": sub.interval.value,
            "created_at": sub.created_at.isoformat(),
        }
