"""SSE endpoint — streams bar updates merging Redis in-progress + Mongo closed bars."""

import asyncio
import json
import time
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pocketquant.api.common.symbol_validation import validate_symbol_pair
from pocketquant.api.market_data.app_services.bar_app_service import BarAppService
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.shared.enums import Interval

router = APIRouter(route_class=DishkaRoute)
logger = get_logger(__name__)

# Poll interval — 1s (200ms throttle + 1s poll ≤ 1.2s max lag)
_POLL_INTERVAL = 1.0


def _make_payload(bar: dict[str, Any], interval: Interval) -> dict[str, Any]:
    """Build unified SSE payload from bar dict (Redis or Mongo fallback shape).

    Redis shape: includes 'last_update' timestamp + 'bar_start' as ISO string.
    Mongo fallback shape: same keys, no 'last_update', tick_count=0.
    is_in_progress=True when sourced from Redis (live in-progress bar).
    staleness_ms=None when Mongo source; ms since last update when Redis source.
    """
    last_update = bar.get("last_update")
    is_in_progress = last_update is not None

    staleness_ms: int | None = None
    if is_in_progress and isinstance(last_update, (int, float)):
        # last_update stored as Unix timestamp (seconds) by BarBuilder.to_dict()
        staleness_ms = max(0, int((time.time() - last_update) * 1000))

    return {
        "symbol": bar.get("symbol"),
        "exchange": bar.get("exchange"),
        "interval": interval.value,
        "bar_start": bar.get("bar_start"),
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "volume": bar.get("volume"),
        "tick_count": bar.get("tick_count", 0),
        "is_in_progress": is_in_progress,
        "staleness_ms": staleness_ms,
    }


@router.get("/bars/stream/{exchange}/{symbol}")
async def stream_bars(
    exchange: str,
    symbol: str,
    request: Request,
    bar_service: FromDishka[BarAppService],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> StreamingResponse:
    """SSE stream — polls Redis (in-progress) + Mongo fallback, emits on change.

    Validates {exchange}/{symbol} path params against SYMBOL_PATTERN (400 on mismatch).
    Validates ?interval against Interval enum; returns 400 with INVALID_INTERVAL
    if unknown value. Existing callers using ?interval=1m are unaffected.
    """
    exchange, symbol = validate_symbol_pair(exchange, symbol)

    async def event_generator():
        last_bar_start: str | None = None
        last_close: float | None = None
        last_volume: float | None = None

        # Emit initial bar immediately on connect
        try:
            bar = await bar_service.get_current_bar(symbol, exchange, interval)
            if bar is not None:
                last_bar_start = bar.get("bar_start")
                last_close = bar.get("close")
                last_volume = bar.get("volume")
                payload = _make_payload(bar, interval)
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            logger.error("sse.bars.init_error", error=str(e))

        # Poll loop — emit when bar_start, close, or volume changes
        try:
            while True:
                await asyncio.sleep(_POLL_INTERVAL)

                bar = await bar_service.get_current_bar(symbol, exchange, interval)
                if bar is None:
                    continue

                bar_start = bar.get("bar_start")
                close = bar.get("close")
                volume = bar.get("volume")

                bar_changed = bar_start != last_bar_start
                ohlcv_changed = close != last_close or volume != last_volume

                if not bar_changed and not ohlcv_changed:
                    continue

                last_bar_start = bar_start
                last_close = close
                last_volume = volume
                yield f"data: {json.dumps(_make_payload(bar, interval))}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("sse.bars.poll_error", error=str(e))

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
