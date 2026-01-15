"""Service for managing real-time quotes and subscriptions."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.common.cache import Cache
from src.common.logging import get_logger
from src.config import Settings
from src.features.market_data.models.quote import Quote, QuoteTick
from src.features.market_data.providers.tradingview_ws import TradingViewWebSocketProvider
from src.features.market_data.services.quote_aggregator import QuoteAggregator

logger = get_logger(__name__)


class QuoteService:
    """Service for managing real-time quote subscriptions.

    This service:
    1. Manages WebSocket connection to TradingView
    2. Caches latest quotes in Redis
    3. Feeds ticks to the aggregator for OHLCV bar creation
    4. Provides API for subscribing/unsubscribing to symbols

    Data Flow:
        TradingView WebSocket → Quote → Redis Cache (latest)
                                     ↘ Aggregator → OHLCV → MongoDB
    """

    # Redis key prefixes
    QUOTE_KEY_PREFIX = "quote:latest:"
    TICK_LIST_PREFIX = "quote:ticks:"

    def __init__(self, settings: Settings):
        """Initialize the quote service.

        Args:
            settings: Application settings.
        """
        self._settings = settings
        self._provider = TradingViewWebSocketProvider()
        self._aggregator = QuoteAggregator()
        self._running = False
        self._ws_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the quote service and WebSocket connection."""
        if self._running:
            logger.warning("quote_service_already_running")
            return

        logger.info("quote_service_starting")
        await self._provider.connect()
        self._running = True
        self._ws_task = asyncio.create_task(self._provider.run_forever())

        logger.info("quote_service_started")

    async def stop(self) -> None:
        """Stop the quote service."""
        logger.info("quote_service_stopping")
        self._running = False
        await self._provider.disconnect()

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        logger.info("quote_service_stopped")

    async def subscribe(self, symbol: str, exchange: str) -> str:
        """Subscribe to real-time quotes for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.

        Returns:
            Subscription key.
        """
        symbol = symbol.upper()
        exchange = exchange.upper()
        key = await self._provider.subscribe(
            symbol=symbol,
            exchange=exchange,
            callback=self._on_quote_update,
        )

        logger.info("quote_subscribed", symbol=symbol, exchange=exchange)
        return key

    async def unsubscribe(self, symbol: str, exchange: str) -> None:
        """Unsubscribe from a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
        """
        await self._provider.unsubscribe(symbol.upper(), exchange.upper())
        symbol_key = f"{exchange}:{symbol}".upper()
        await Cache.delete(f"{self.QUOTE_KEY_PREFIX}{symbol_key}")

        logger.info("quote_unsubscribed", symbol=symbol, exchange=exchange)

    async def _on_quote_update(self, quote_data: dict[str, Any]) -> None:
        """Handle incoming quote update.

        Args:
            quote_data: Quote data from WebSocket.
        """
        symbol_key = quote_data.get("symbol_key", "")
        if not symbol_key or ":" not in symbol_key:
            return

        exchange, symbol = symbol_key.split(":", 1)

        # Skip if no price
        last_price = quote_data.get("last_price")
        if last_price is None:
            return

        quote = Quote(
            symbol=symbol,
            exchange=exchange,
            timestamp=quote_data.get("timestamp", datetime.now(UTC)),
            last_price=last_price,
            bid=quote_data.get("bid"),
            ask=quote_data.get("ask"),
            volume=quote_data.get("volume"),
            change=quote_data.get("change"),
            change_percent=quote_data.get("change_percent"),
            open_price=quote_data.get("open_price"),
            high_price=quote_data.get("high_price"),
            low_price=quote_data.get("low_price"),
            prev_close=quote_data.get("prev_close"),
        )

        cache_key = f"{self.QUOTE_KEY_PREFIX}{symbol_key}"
        await Cache.set(cache_key, quote.to_cache_dict(), ttl=60)

        tick = QuoteTick(
            symbol=symbol,
            exchange=exchange,
            timestamp=quote.timestamp,
            price=last_price,
            volume=quote_data.get("volume"),
        )
        await self._aggregator.add_tick(tick)

        logger.debug(
            "quote_received",
            symbol=symbol_key,
            price=last_price,
        )

    async def get_latest_quote(self, symbol: str, exchange: str) -> Quote | None:
        """Get the latest cached quote for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.

        Returns:
            Latest Quote or None if not available.
        """
        symbol_key = f"{exchange}:{symbol}".upper()
        cache_key = f"{self.QUOTE_KEY_PREFIX}{symbol_key}"

        data = await Cache.get(cache_key)
        if data:
            return Quote.from_cache_dict(data)

        return None

    async def get_all_quotes(self) -> list[Quote]:
        """Get all currently cached quotes.

        Returns:
            List of all cached quotes.
        """
        # Redis SCAN can be slow with many keys; consider maintaining a set of active subscriptions
        quotes = []
        for symbol_key in self._provider._subscriptions.keys():
            cache_key = f"{self.QUOTE_KEY_PREFIX}{symbol_key}"
            data = await Cache.get(cache_key)
            if data:
                quotes.append(Quote.from_cache_dict(data))

        return quotes

    def is_running(self) -> bool:
        """Check if the service is running.

        Returns:
            True if running, False otherwise.
        """
        return self._running and self._provider.is_connected()

    @property
    def subscription_count(self) -> int:
        """Get number of active subscriptions."""
        return self._provider.subscription_count

    def get_aggregator(self) -> QuoteAggregator:
        """Get the quote aggregator instance.

        Returns:
            The QuoteAggregator instance.
        """
        return self._aggregator


# Global service instance (singleton pattern for the WebSocket connection)
_quote_service: QuoteService | None = None


def get_quote_service(settings: Settings) -> QuoteService:
    """Get the global quote service instance.

    Args:
        settings: Application settings.

    Returns:
        The global QuoteService instance.
    """
    global _quote_service

    if _quote_service is None:
        _quote_service = QuoteService(settings)

    return _quote_service
