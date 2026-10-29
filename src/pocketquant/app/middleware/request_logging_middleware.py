import logging
import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pocketquant.core.common.logging import get_logger

logger = get_logger(__name__)

SKIP_PATHS = {"/health", "/favicon.ico"}
MAX_BODY_LOG_SIZE = 10_000


# DEBUG only: a per-request INFO line scales with traffic (the SPA polls every few
# seconds). A body is read only when it will be printed: it costs a rebuilt response.
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        debug = logging.getLogger(__name__).isEnabledFor(logging.DEBUG)
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        if debug and method in {"POST", "PUT", "PATCH"}:
            body_bytes = await request.body()
            if body_bytes:
                body = body_bytes[:MAX_BODY_LOG_SIZE].decode(errors="replace")
                logger.debug("http.request.body", path=path, body=body)

        response = await call_next(request)

        # An SSE body never ends: reading it here would hold the whole response
        # back until the client disconnects. Judged by the response, not a route
        # list, so a new stream route cannot be missed.
        is_streaming = response.headers.get("content-type", "").startswith("text/event-stream")
        if debug and not is_streaming:
            if hasattr(response, "body"):
                body_bytes = response.body
            else:
                body_bytes = b"".join([chunk async for chunk in response.body_iterator])
                response = Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            body = body_bytes[:MAX_BODY_LOG_SIZE].decode(errors="replace")
            logger.debug("http.response.body", path=path, body=body)

        logger.debug(
            "http.request",
            method=method,
            path=path,
            query=str(request.query_params) if request.query_params else None,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
        )
        return response
