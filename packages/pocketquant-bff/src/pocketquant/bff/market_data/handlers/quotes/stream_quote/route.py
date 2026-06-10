"""SSE endpoint — streams real-time quote updates by polling Redis quote:latest.

Path: GET /stream/{symbol}
``{symbol}`` is URL-encoded composite, e.g. ``BTCUSDT%3ABINANCE``.
"""

import asyncio
import json
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pocketquant.bff.common.symbol_validation import validate_composite_symbol
from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST
from pocketquant.core.common.logging import get_logger
from pocketquant.core.persistence.redis import Cache

router = APIRouter(route_class=DishkaRoute)
logger = get_logger(__name__)

# Poll interval — 500ms; combined with 200ms Redis write throttle keeps max lag < 700ms
_POLL_INTERVAL = 0.5


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
    request: Request,
    cache: FromDishka[Cache],
) -> StreamingResponse:
    """SSE stream — polls Redis quote:latest every 500ms, emits on last_price or volume change.

    ``{symbol}`` path param is URL-encoded composite (e.g. ``BTCUSDT%3ABINANCE``).
    Validates composite format (400 on mismatch).
    """
    symbol = validate_composite_symbol(symbol)
    cache_key = CACHE_KEY_QUOTE_LATEST.format(symbol=symbol)

    async def event_generator():
        last_price: float | None = None
        last_volume: float | None = None

        # Emit initial quote immediately on connect
        try:
            quote = await cache.get(cache_key)
            if quote is not None:
                last_price = quote.get("last_price")
                last_volume = quote.get("volume")
                yield f"data: {json.dumps(_make_payload(quote))}\n\n"
        except Exception as e:
            logger.error("sse.quote.init_error", error=str(e))

        # Poll loop — emit only when last_price or volume changes
        try:
            while True:
                await asyncio.sleep(_POLL_INTERVAL)

                quote = await cache.get(cache_key)
                if quote is None:
                    continue

                current_price = quote.get("last_price")
                current_volume = quote.get("volume")

                price_changed = current_price != last_price
                volume_changed = current_volume != last_volume

                if not price_changed and not volume_changed:
                    continue

                last_price = current_price
                last_volume = current_volume
                yield f"data: {json.dumps(_make_payload(quote))}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("sse.quote.poll_error", error=str(e))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )
