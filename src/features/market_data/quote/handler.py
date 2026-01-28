"""Handlers for quote commands and queries."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_QUOTE_LATEST, TTL_QUOTE_LATEST
from src.common.logging import get_logger
from src.common.mediator import Handler
from src.config import Settings
from src.features.market_data.managers.bar_manager import BarManager
from src.features.market_data.models.quote import Quote, QuoteTick
from src.features.market_data.providers import TradingViewWebSocketProvider
from src.features.market_data.quote.command import (
    StartQuoteFeedCommand,
    StopQuoteFeedCommand,
    SubscribeCommand,
    UnsubscribeCommand,
)
from src.features.market_data.quote.dto import QuoteResult
from src.features.market_data.quote.query import GetAllQuotesQuery, GetLatestQuoteQuery

logger = get_logger(__name__)


class QuoteServiceState:
    """Shared state for quote service."""

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


_quote_state: QuoteServiceState | None = None


def get_quote_state(settings: Settings) -> QuoteServiceState:
    """Get or create the shared quote service state."""
    global _quote_state

    if _quote_state is None:
        _quote_state = QuoteServiceState(settings)

    return _quote_state


class StartQuoteFeedHandler(Handler[StartQuoteFeedCommand, dict]):
    """Handle starting the quote feed."""

    def __init__(self, settings: Settings):
        self.state = get_quote_state(settings)

    async def handle(self, cmd: StartQuoteFeedCommand) -> dict:
        if self.state.running:
            logger.warning("quote_service.already_running")
            return {
                "status": "already_running",
                "message": "Quote service is already running",
            }

        logger.info("quote_service.starting")
        await self.state.provider.connect()
        self.state.running = True
        self.state.ws_task = asyncio.create_task(self.state.provider.run_forever())

        logger.info("quote_service.started")
        return {"status": "started", "message": "Quote service started"}


class StopQuoteFeedHandler(Handler[StopQuoteFeedCommand, dict]):
    """Handle stopping the quote feed."""

    def __init__(self, settings: Settings):
        self.state = get_quote_state(settings)

    async def handle(self, cmd: StopQuoteFeedCommand) -> dict:
        if not self.state.running:
            return {"status": "not_running", "message": "Quote service is not running"}

        logger.info("quote_service.stopping")

        saved_count = await self.state.bar_manager.flush_all_bars()

        self.state.running = False
        await self.state.provider.disconnect()

        if self.state.ws_task:
            self.state.ws_task.cancel()
            try:
                await self.state.ws_task
            except asyncio.CancelledError:
                pass

        logger.info("quote_service.stopped")
        return {
            "status": "stopped",
            "message": "Quote service stopped",
            "bars_saved": saved_count,
        }


class SubscribeHandler(Handler[SubscribeCommand, dict]):
    """Handle subscribing to a symbol."""

    def __init__(self, settings: Settings):
        self.state = get_quote_state(settings)

    async def handle(self, cmd: SubscribeCommand) -> dict:
        if not self.state.running or not self.state.provider.is_connected():
            raise ValueError(
                "Quote service not running. Start it first via StartQuoteFeedCommand"
            )

        symbol = cmd.symbol.upper()
        exchange = cmd.exchange.upper()

        key = await self.state.provider.subscribe(
            symbol=symbol,
            exchange=exchange,
            callback=self.state.on_quote_update,
        )

        logger.info("quote_service.subscribed", symbol=symbol, exchange=exchange)
        return {
            "subscription_key": key,
            "message": f"Subscribed to {key}",
        }


class UnsubscribeHandler(Handler[UnsubscribeCommand, dict]):
    """Handle unsubscribing from a symbol."""

    def __init__(self, settings: Settings):
        self.state = get_quote_state(settings)

    async def handle(self, cmd: UnsubscribeCommand) -> dict:
        symbol = cmd.symbol.upper()
        exchange = cmd.exchange.upper()

        await self.state.provider.unsubscribe(symbol, exchange)
        cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
        await Cache.delete(cache_key)

        logger.info("quote_service.unsubscribed", symbol=symbol, exchange=exchange)
        return {"message": f"Unsubscribed from {exchange}:{symbol}"}


class GetLatestQuoteHandler(Handler[GetLatestQuoteQuery, QuoteResult | None]):
    """Handle getting the latest quote for a symbol."""

    async def handle(self, query: GetLatestQuoteQuery) -> QuoteResult | None:
        cache_key = CACHE_KEY_QUOTE_LATEST.format(
            exchange=query.exchange.upper(), symbol=query.symbol.upper()
        )

        data = await Cache.get(cache_key)
        if data:
            quote = Quote.from_cache_dict(data)
            return QuoteResult.from_quote(quote)

        return None


class GetAllQuotesHandler(Handler[GetAllQuotesQuery, list[QuoteResult]]):
    """Handle getting all active quotes."""

    def __init__(self, settings: Settings):
        self.state = get_quote_state(settings)

    async def handle(self, query: GetAllQuotesQuery) -> list[QuoteResult]:
        quotes = []
        for symbol_key in self.state.provider._subscriptions.keys():
            exchange, symbol = symbol_key.split(":", 1)
            cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
            data = await Cache.get(cache_key)
            if data:
                quote = Quote.from_cache_dict(data)
                quotes.append(QuoteResult.from_quote(quote))

        return quotes
