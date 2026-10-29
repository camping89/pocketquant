import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi.responses import StreamingResponse

from pocketquant.core.common.logging import get_logger

logger = get_logger(__name__)


# A fetch error ends the stream with one log line; the browser's EventSource
# reconnects.
def poll_stream(
    name: str,
    fetch: Callable[[], Awaitable[dict | None]],
    change_key: Callable[[dict], Any],
    payload: Callable[[dict], dict],
    interval_s: float,
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        last: Any = None
        try:
            while True:
                item = await fetch()
                if item is not None and (key := change_key(item)) != last:
                    last = key
                    yield f"data: {json.dumps(payload(item))}\n\n"
                await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"sse.{name}.poll_error", error=str(e))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
