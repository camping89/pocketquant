"""Quotes routes — latest quote lookup, current bar, and SSE stream."""

from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from pocketquant.app.common.sse_poll import poll_stream
from pocketquant.app.common.symbol_validation import validate_composite_symbol
from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.quotes_service import QuoteQueryService, QuoteResponse

router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"], route_class=DishkaRoute)
logger = get_logger(__name__)

# Poll interval — 500ms; combined with 200ms Redis write throttle keeps max lag < 700ms
_POLL_INTERVAL = 0.5


@router.get("/latest/{symbol}", response_model=QuoteResponse)
async def get_latest_quote(
    symbol: str,
    quote_service: FromDishka[QuoteQueryService],
) -> QuoteResponse:
    symbol = validate_composite_symbol(symbol)
    result = await quote_service.get_latest(symbol)

    if result is None:
        raise NotFoundError(f"No quote found for {symbol}. Make sure you're subscribed.")

    return result


@router.get("/current-bar/{symbol}")
async def get_current_bar(
    symbol: str,
    bar_service: FromDishka[BarAppService],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    # Reads the current bar straight from Cache (live feed writes it) with a
    # DB fallback — no WS-runtime coupling in the read path.
    symbol = validate_composite_symbol(symbol)
    bar = await bar_service.get_current_bar(symbol, interval)

    if bar is None:
        raise NotFoundError(f"No current bar for {symbol} at {interval.value}")

    return bar


def _make_payload(quote: dict[str, Any]) -> dict[str, Any]:
    """Build SSE payload from Redis quote:latest dict (written by QuoteAppService)."""
    return {
        "symbol": quote.get("symbol"),
        "last_price": quote.get("last_price"),
        "bid": quote.get("bid"),
        "ask": quote.get("ask"),
        "volume": quote.get("volume"),
        "change": quote.get("change"),
        "change_percent": quote.get("change_percent"),
        "ts": quote.get("timestamp"),
    }


@router.get("/stream/{symbol}")
async def stream_quote(
    symbol: str,
    cache: FromDishka[Cache],
) -> StreamingResponse:
    """SSE stream — polls Redis quote:latest every 500ms, emits on last_price or volume change.

    ``{symbol}`` path param is URL-encoded composite (e.g. ``BTCUSDT%3ABINANCE``).
    Validates composite format (400 on mismatch).
    """
    symbol = validate_composite_symbol(symbol)
    cache_key = CACHE_KEY_QUOTE_LATEST.format(symbol=symbol)
    return poll_stream(
        "quote",
        lambda: cache.get(cache_key),
        lambda quote: (quote.get("last_price"), quote.get("volume")),
        _make_payload,
        _POLL_INTERVAL,
    )
