"""WsSubscriptionManager — reconciles WS subscriptions against tracked_symbols every 5s.

Runs as a background task (asyncio.Task) spawned in lifespan.
Idempotent: subscribe/unsubscribe only diffs (desired vs current).
Cancel-safe: CancelledError propagates cleanly so lifespan teardown works.
"""

import asyncio

from pocketquant.core.common.logging import get_logger
from pocketquant.core.infrastructure.realtime_quote_provider import IRealtimeQuoteProvider
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger(__name__)

# Rate-limit burst subscriptions: cap at 50/sec → 20ms between calls
_SUBSCRIBE_DELAY_S = 0.02


class WsSubscriptionManager:
    """Reconciles live WS subscriptions against the tracked_symbols collection.

    Args:
        provider: Realtime WS client (singleton, shared with QuoteAppService).
        tracked_symbol_repo: MongoDB repository for tracked symbols.
        quote_app_service: Provides the on_quote_update callback registered per symbol.
        interval_s: Reconcile interval in seconds (default 5.0).
    """

    def __init__(
        self,
        provider: IRealtimeQuoteProvider,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,  # type: ignore[name-defined]  # noqa: F821 — forward ref avoids circular import
        interval_s: float = 5.0,
    ):
        self._provider = provider
        self._repo = tracked_symbol_repo
        self._quote_app_service = quote_app_service
        self._interval_s = interval_s

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
        """Diff desired vs current subscriptions and apply changes."""
        tracked = await self._repo.list_all()
        # Build desired set as "EXCHANGE:SYMBOL" keys (uppercase — matches provider format)
        desired: set[str] = {f"{ts.exchange}:{ts.symbol}".upper() for ts in tracked}
        current: set[str] = set(self._provider.subscriptions.keys())

        to_add = desired - current
        to_remove = current - desired

        if not to_add and not to_remove:
            return

        for symbol_key in to_add:
            exchange, symbol = symbol_key.split(":", 1)
            try:
                await self._provider.subscribe(
                    symbol=symbol,
                    exchange=exchange,
                    callback=self._quote_app_service.on_quote_update,
                )
                # Rate-limit burst subscriptions to avoid provider IP-ban
                await asyncio.sleep(_SUBSCRIBE_DELAY_S)
            except Exception as exc:
                logger.warning(
                    "ws_subscription_manager.subscribe_failed",
                    symbol=symbol_key,
                    error=str(exc),
                )

        for symbol_key in to_remove:
            exchange, symbol = symbol_key.split(":", 1)
            try:
                await self._provider.unsubscribe(symbol=symbol, exchange=exchange)
            except Exception as exc:
                logger.warning(
                    "ws_subscription_manager.unsubscribe_failed",
                    symbol=symbol_key,
                    error=str(exc),
                )

        logger.info(
            "ws_subscription_manager.reconciled",
            added=len(to_add),
            removed=len(to_remove),
        )
