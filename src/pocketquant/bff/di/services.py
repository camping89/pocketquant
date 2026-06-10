"""Feature-service provider for bff — services routes inject directly.

Replaces per-endpoint CQRS handlers: each feature area exposes one service
class; routes call its methods via FromDishka injection.
"""

from dishka import Provider, Scope, provide

from pocketquant.engine.market_data.tracked_symbols_backfill import TrackedSymbolBackfillService
from pocketquant.engine.market_data.tracked_symbols_service import TrackedSymbolService


class BffServiceProvider(Provider):
    tracked_symbol_service = provide(TrackedSymbolService, scope=Scope.APP)
    tracked_symbol_backfill_service = provide(TrackedSymbolBackfillService, scope=Scope.APP)
