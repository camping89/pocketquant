"""QuoteAppService manages the WebSocket feed, subscriptions, and tick processing."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from pocketquant.api.market_data.app_services.bar_app_service import BarAppService
from pocketquant.api.market_data.app_services.quote_dto import Quote, QuoteTick
from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST, TTL_QUOTE_LATEST
from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.infrastructure.tradingview import TradingViewWebSocketClient
from pocketquant.core.persistence.redis import Cache

logger = get_logger(__name__)


class QuoteAppService:
    """Manages quote WebSocket feed, subscriptions, and tick processing."""

    def __init__(
        self,
        settings: Settings,
        cache: Cache,
        bar_manager: BarAppService,
        provider: TradingViewWebSocketClient,
    ):
        self.settings = settings
        self._cache = cache
        self.provider = provider
        self.bar_manager = bar_manager
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
        await self._cache.set(cache_key, quote.to_cache_dict(), ttl=TTL_QUOTE_LATEST)

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

    async def start(self) -> None:
        """Start the WS feed as a background task. Idempotent — no-op if already running."""
        if self.running:
            logger.debug("quote_service.already_running")
            return

        self.running = True
        self.ws_task = asyncio.create_task(self.provider.run_forever())
        logger.info("quote_service.ws_task_started")
