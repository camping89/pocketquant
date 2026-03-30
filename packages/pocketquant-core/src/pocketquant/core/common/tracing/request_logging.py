"""Request/Response logging middleware."""

import time
from collections.abc import Callable

from pocketquant.core.common.logging import get_logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = get_logger(__name__)

SKIP_PATHS = {"/health", "/favicon.ico"}
# SSE endpoints must not have their body_iterator consumed — skip logging body for these
SKIP_BODY_PREFIXES = ("/api/v1/market-data/bars/stream",)
MAX_BODY_LOG_SIZE = 10_000


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs HTTP request and response details including bodies."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        start_time = time.perf_counter()
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else None

        request_body = None
        if method in {"POST", "PUT", "PATCH"}:
            body_bytes = await request.body()
            if body_bytes:
                request_body = body_bytes[:MAX_BODY_LOG_SIZE].decode(errors="replace")

        logger.info(
            "http.request",
            method=method,
            path=path,
            query=query,
            body=request_body,
            client=request.client.host if request.client else None,
        )

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        # SSE and other streaming responses must not have body_iterator consumed
        is_streaming = path.startswith(SKIP_BODY_PREFIXES)

        response_body = None
        if not is_streaming:
            if hasattr(response, "body"):
                response_body = response.body[:MAX_BODY_LOG_SIZE].decode(errors="replace")
            else:
                body_chunks = []
                async for chunk in response.body_iterator:
                    body_chunks.append(chunk)
                response_body_bytes = b"".join(body_chunks)
                response_body = response_body_bytes[:MAX_BODY_LOG_SIZE].decode(errors="replace")

                response = Response(
                    content=response_body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

        logger.info(
            "http.response",
            method=method,
            path=path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
            body=response_body,
        )

        return response
