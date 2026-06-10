"""Strategy template + subscription API route aggregators.

Two top-level routers:

* ``strategy_router`` (prefix ``/strategies``)         — template-scoped operations
* ``subscription_router`` (prefix ``/subscriptions``)  — subscription-instance operations

Template-scoped:
    GET    /                                  list registered templates
    GET    /{strategy_code}                   template metadata
    POST   /{strategy_code}/subscriptions     create a subscription
    DELETE /{strategy_code}                   cascade delete template + all subs

Subscription-scoped:
    GET    /                                  list subscriptions (?strategy_code=)
    POST   /{sub_id}/start                    start the runtime strategy instance
    POST   /{sub_id}/stop                     stop it
    DELETE /{sub_id}                          remove this single subscription
    GET    /{sub_id}/positions                open positions for this sub
    GET    /{sub_id}/trades                   trades for this sub
    GET    /{sub_id}/backtest                 latest backtest result for this sub
"""

from fastapi import APIRouter

from pocketquant.trading.handlers.strategy.add_symbol.route import (
    router as create_subscription_router,
)
from pocketquant.trading.handlers.strategy.delete.route import router as delete_strategy_router
from pocketquant.trading.handlers.strategy.get_all.route import router as list_templates_router
from pocketquant.trading.handlers.strategy.get_one.route import router as get_template_router
from pocketquant.trading.handlers.strategy.get_positions.route import (
    router as get_positions_router,
)
from pocketquant.trading.handlers.strategy.get_subscription_backtest.route import (
    router as get_subscription_backtest_router,
)
from pocketquant.trading.handlers.strategy.get_trades.route import (
    router as get_trades_router,
)
from pocketquant.trading.handlers.strategy.list_symbols.route import (
    router as list_subscriptions_router,
)
from pocketquant.trading.handlers.strategy.remove_symbol.route import (
    router as remove_subscription_router,
)
from pocketquant.trading.handlers.strategy.start.route import router as start_subscription_router
from pocketquant.trading.handlers.strategy.stop.route import router as stop_subscription_router

router = APIRouter(prefix="/strategies", tags=["strategies"])
router.include_router(list_templates_router)
router.include_router(get_template_router)
router.include_router(create_subscription_router)
router.include_router(delete_strategy_router)

subscription_router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
subscription_router.include_router(list_subscriptions_router)
subscription_router.include_router(start_subscription_router)
subscription_router.include_router(stop_subscription_router)
subscription_router.include_router(get_positions_router)
subscription_router.include_router(get_trades_router)
subscription_router.include_router(get_subscription_backtest_router)
subscription_router.include_router(remove_subscription_router)
