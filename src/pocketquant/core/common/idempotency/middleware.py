"""Idempotency middleware with Redis-backed response caching."""

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pocketquant.core.common.constants import HEADER_IDEMPOTENCY_KEY


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Cache responses for POST/PATCH requests with Idempotency-Key header."""

    TTL = 86400  # 24 hours

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method not in ["POST", "PATCH"]:
            return await call_next(request)

        idempotency_key = request.headers.get(HEADER_IDEMPOTENCY_KEY)
        if not idempotency_key:
            return await call_next(request)

        cache = request.app.state.cache
        cache_key = f"idempotent:{idempotency_key}"
        cached = await cache.get(cache_key)

        if cached:
            return Response(
                content=cached["body"],
                status_code=cached["status"],
                headers=cached["headers"],
            )

        response = await call_next(request)
        response_body = b""
        # StreamingResponse has body_iterator attribute
        body_iter = getattr(response, "body_iterator", None)
        if body_iter is not None:
            async for chunk in body_iter:
                response_body += chunk

        await cache.set(
            cache_key,
            {
                "body": response_body.decode(),
                "status": response.status_code,
                "headers": dict(response.headers),
            },
            ttl=self.TTL,
        )

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
