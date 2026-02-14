"""QuoteService manages the WebSocket feed, subscriptions, and tick processing."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.application.market_data.bar_manager import BarManager
from src.common.cache import Cache
from src.common.constants import CACHE_KEY_QUOTE_LATEST, TTL_QUOTE_LATEST
from src.common.logging import get_logger
from src.config import Settings
from src.infrastructure.tradingview import TradingViewWebSocketProvider
from src.persistence.schemas.quote_schema import Quote, QuoteTick

logger = get_logger(__name__)


class QuoteService:
    """Manages quote WebSocket feed, subscriptions, and tick processing."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = TradingViewWebSocketProvider()
        self.bar_manager = BarManager()
        self.running = False
        self.ws_task: asyncio.Task | None = None

    async def on_quote_update(self, quote_data: dict[str, Any]) -> None:
        """Handle incoming quote updates."""
        symbol_key = quote_data.get("symbol_key", "")
        if not symbol_key or ":" not in symbol_key:
            return

        exchange, symbol = symbol_key.split(":", 1)

        last_price = quote_data.get("last_price")
        if last_price is None:
            return

        quote = Quote(
            symbol=symbol,
            exchange=exchange,
            timestamp=quote_data.get("timestamp", datetime.now(UTC)),
            lp=last_price,
            bid=quote_data.get("bid"),
            ask=quote_data.get("ask"),
            volume=quote_data.get("volume"),
            ch=quote_data.get("change"),
            chp=quote_data.get("change_percent"),
            open_price=quote_data.get("open_price"),
            high_price=quote_data.get("high_price"),
            low_price=quote_data.get("low_price"),
            prev_close=quote_data.get("prev_close"),
        )

        cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
        await Cache.set(cache_key, quote.to_cache_dict(), ttl=TTL_QUOTE_LATEST)

        tick = QuoteTick(
            symbol=symbol,
            exchange=exchange,
            timestamp=quote.timestamp,
            price=last_price,
            volume=quote_data.get("volume"),
        )
        await self.bar_manager.add_tick(tick)

        logger.debug(
            "quote_service.tick_received",
            symbol=symbol_key,
            price=last_price,
        )


_quote_service: QuoteService | None = None


def get_quote_service(settings: Settings) -> QuoteService:
    """Get or create the shared quote service."""
    global _quote_service

    if _quote_service is None:
        _quote_service = QuoteService(settings)

    return _quote_service
