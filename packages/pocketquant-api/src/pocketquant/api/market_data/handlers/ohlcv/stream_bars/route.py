"""SSE endpoint — streams bar updates by polling MongoDB for new/updated bars."""

import asyncio
import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

router = APIRouter(route_class=DishkaRoute)
logger = get_logger(__name__)

# Poll interval in seconds — balances latency vs DB load
_POLL_INTERVAL = 2.0


@router.get("/bars/stream/{exchange}/{symbol}")
async def stream_bars(
    exchange: str,
    symbol: str,
    interval: Interval,
    request: Request,
    bar_repository: FromDishka[BarRepository],
) -> StreamingResponse:
    """SSE stream — polls DB every 2s, emits when the latest bar changes."""

    async def event_generator():
        last_bar_start: str | None = None
        last_close: float | None = None
        last_volume: float | None = None

        def _make_payload(bar, bar_start: str) -> dict:
            return {
                "symbol": bar.symbol,
                "exchange": bar.exchange,
                "interval": interval.value,
                "bar_start": bar_start,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "tick_count": bar.tick_count,
            }

        # Send initial bar immediately on connect
        try:
            bar = await bar_repository.get_latest(symbol, exchange, interval)
            if bar is not None:
                last_bar_start = bar.datetime.isoformat()
                last_close = bar.close
                last_volume = bar.volume
                yield f"data: {json.dumps(_make_payload(bar, last_bar_start))}\n\n"
        except Exception as e:
            logger.error("sse.init_error", error=str(e))

        # Poll loop — emit when bar_start changes OR OHLCV updates (in-progress bar)
        try:
            while True:
                await asyncio.sleep(_POLL_INTERVAL)

                bar = await bar_repository.get_latest(symbol, exchange, interval)
                if bar is None:
                    continue

                bar_start = bar.datetime.isoformat()
                bar_changed = bar_start != last_bar_start
                ohlcv_changed = bar.close != last_close or bar.volume != last_volume

                if not bar_changed and not ohlcv_changed:
                    continue

                last_bar_start = bar_start
                last_close = bar.close
                last_volume = bar.volume
                yield f"data: {json.dumps(_make_payload(bar, bar_start))}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("sse.poll_error", error=str(e))

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
