"""Idempotency middleware with Redis-backed response caching."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.common.constants import HEADER_IDEMPOTENCY_KEY
from src.infrastructure.persistence import Cache


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Cache responses for POST/PATCH requests with Idempotency-Key header."""

    TTL = 86400  # 24 hours

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in ["POST", "PATCH"]:
            return await call_next(request)

        idempotency_key = request.headers.get(HEADER_IDEMPOTENCY_KEY)
        if not idempotency_key:
            return await call_next(request)

        cache_key = f"idempotent:{idempotency_key}"
        cached = await Cache.get(cache_key)

        if cached:
            return Response(
                content=cached["body"],
                status_code=cached["status"],
                headers=cached["headers"],
            )

        response = await call_next(request)
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        await Cache.set(
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
