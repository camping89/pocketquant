"""WsSubscriptionAppService — reconciles WS subscriptions against tracked_symbols every 5s.

Runs as a background task (asyncio.Task) spawned in lifespan.
Idempotent: subscribe/unsubscribe only diffs (desired vs current).
Cancel-safe: CancelledError propagates cleanly so lifespan teardown works.
``symbol`` keys are composite ``{code}:{exchange}`` throughout.
"""

import asyncio

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger(__name__)

# Rate-limit burst subscriptions: cap at 50/sec → 20ms between calls
_SUBSCRIBE_DELAY_S = 0.02


class WsSubscriptionAppService:
    """Reconciles live WS subscriptions against the tracked_symbols collection.

    Args:
        provider: Realtime WS client (singleton, shared with QuoteAppService).
        tracked_symbol_repo: MongoDB repository for tracked symbols.
        quote_app_service: Provides the on_quote_update callback registered per symbol.
        interval_s: Reconcile interval in seconds (default 5.0).
    """

    def __init__(
        self,
        provider: IRealtimeQuoteProviderPort,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,  # type: ignore[name-defined]  # noqa: F821 — forward ref avoids circular import
        interval_s: float = 5.0,
    ):
        self._provider = provider
        self._repo = tracked_symbol_repo
        self._quote_app_service = quote_app_service
        self._interval_s = interval_s
        # Symbols whose subscribe failure has already been logged at WARNING. A
        # symbol no realtime provider serves (index futures before a quote
        # adapter exists) fails every tick, so repeating the WARNING every 5s
        # would flood the log with a state that is configured, not transient.
        self._warned_subscribe_failed: set[str] = set()

    async def run(self) -> None:
        """Async reconcile loop. Runs until cancelled by lifespan shutdown."""
        logger.info("ws_subscription_manager.started", interval_s=self._interval_s)

        while True:
            try:
                await self._reconcile()
            except asyncio.CancelledError:
                # Propagate cancellation — lifespan is shutting down
                logger.info("ws_subscription_manager.cancelled")
                raise
            except Exception as exc:
                # Log and retry next tick — never crash the app
                logger.error("ws_subscription_manager.reconcile_failed", error=str(exc))

            await asyncio.sleep(self._interval_s)

    async def _reconcile(self) -> None:
        tracked = await self._repo.list_all()
        # tracked_symbols store composite symbol; uppercase to match provider format
        desired: set[str] = {ts.symbol.upper() for ts in tracked}
        current: set[str] = set(self._provider.subscriptions.keys())

        to_add = desired - current
        to_remove = current - desired
        # An untracked symbol warns afresh if it is tracked again later.
        self._warned_subscribe_failed &= desired

        if not to_add and not to_remove:
            return

        added = 0
        for symbol_key in to_add:
            try:
                await self._provider.subscribe(
                    symbol=symbol_key,
                    callback=self._quote_app_service.on_quote_update,
                )
                added += 1
                self._warned_subscribe_failed.discard(symbol_key)
                # Rate-limit burst subscriptions to avoid provider IP-ban
                await asyncio.sleep(_SUBSCRIBE_DELAY_S)
            except Exception as exc:
                if symbol_key in self._warned_subscribe_failed:
                    logger.debug(
                        "ws_subscription_manager.subscribe_failed",
                        symbol=symbol_key,
                        error=str(exc),
                    )
                else:
                    self._warned_subscribe_failed.add(symbol_key)
                    logger.warning(
                        "ws_subscription_manager.subscribe_failed",
                        symbol=symbol_key,
                        error=str(exc),
                    )

        removed = 0
        for symbol_key in to_remove:
            try:
                await self._provider.unsubscribe(symbol=symbol_key)
                removed += 1
            except Exception as exc:
                logger.warning(
                    "ws_subscription_manager.unsubscribe_failed",
                    symbol=symbol_key,
                    error=str(exc),
                )

        # Counts what changed, not what was attempted: a symbol that fails every
        # tick would otherwise log a phantom INFO change every 5s.
        if added or removed:
            logger.info(
                "ws_subscription_manager.reconciled",
                added=added,
                removed=removed,
            )
