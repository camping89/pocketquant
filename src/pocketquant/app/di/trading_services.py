"""Trading feature service providers for the app process.

StrategyCommandService and StrategyQueryService are registered here so the app
has them if routes run in the same process. OrderPositionQueryService requires
OrderAppService / PositionAppService (in-RAM engine state) — it is only
meaningful in the app process and is excluded from the stateless bff.
"""

from dishka import Provider, Scope, provide

from pocketquant.trading.orders_positions_service import OrderPositionQueryService
from pocketquant.trading.strategy_command_service import StrategyCommandService
from pocketquant.trading.strategy_query_service import StrategyQueryService


class AppTradingServiceProvider(Provider):
    strategy_command_service = provide(StrategyCommandService, scope=Scope.APP)
    strategy_query_service = provide(StrategyQueryService, scope=Scope.APP)
    # Requires OrderAppService + PositionAppService — only resolvable in app process.
    order_position_query_service = provide(OrderPositionQueryService, scope=Scope.APP)
