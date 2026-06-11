"""Trading feature service providers.

OrderPositionQueryService requires OrderAppService / PositionAppService
(in-RAM engine state) — its answers reflect the running execution engine.
"""

from dishka import Provider, Scope, provide

from pocketquant.engine.orders_positions_service import OrderPositionQueryService
from pocketquant.engine.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy_query_service import StrategyQueryService


class AppTradingServiceProvider(Provider):
    strategy_command_service = provide(StrategyCommandService, scope=Scope.APP)
    strategy_query_service = provide(StrategyQueryService, scope=Scope.APP)
    order_position_query_service = provide(OrderPositionQueryService, scope=Scope.APP)
