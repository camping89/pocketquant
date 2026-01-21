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
    QUOTE_KEY_PREFIX = "quote:latest:"
    TICK_LIST_PREFIX = "quote:ticks:"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._provider = TradingViewWebSocketProvider()
        self._aggregator = QuoteAggregator()
        self._running = False
        self._ws_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            logger.warning("quote_service_already_running")
            return

        logger.info("quote_service_starting")
        await self._provider.connect()
        self._running = True
        self._ws_task = asyncio.create_task(self._provider.run_forever())

        logger.info("quote_service_started")

    async def stop(self) -> None:
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
        await self._provider.unsubscribe(symbol.upper(), exchange.upper())
        symbol_key = f"{exchange}:{symbol}".upper()
        await Cache.delete(f"{self.QUOTE_KEY_PREFIX}{symbol_key}")

        logger.info("quote_unsubscribed", symbol=symbol, exchange=exchange)

    async def _on_quote_update(self, quote_data: dict[str, Any]) -> None:
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
        symbol_key = f"{exchange}:{symbol}".upper()
        cache_key = f"{self.QUOTE_KEY_PREFIX}{symbol_key}"

        data = await Cache.get(cache_key)
        if data:
            return Quote.from_cache_dict(data)

        return None

    async def get_all_quotes(self) -> list[Quote]:
        quotes = []
        for symbol_key in self._provider._subscriptions.keys():
            cache_key = f"{self.QUOTE_KEY_PREFIX}{symbol_key}"
            data = await Cache.get(cache_key)
            if data:
                quotes.append(Quote.from_cache_dict(data))

        return quotes

    def is_running(self) -> bool:
        return self._running and self._provider.is_connected()

    @property
    def subscription_count(self) -> int:
        return self._provider.subscription_count

    def get_aggregator(self) -> QuoteAggregator:
        return self._aggregator


_quote_service: QuoteService | None = None


def get_quote_service(settings: Settings) -> QuoteService:
    global _quote_service

    if _quote_service is None:
        _quote_service = QuoteService(settings)

    return _quote_service
