"""Rate limiting with token bucket algorithm."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.persistence import Cache


class TokenBucket:
    """Token bucket for rate limiting with refill."""

    def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Consume tokens if available."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client-IP rate limiting via Redis."""

    def __init__(self, app, capacity: int = 200, refill_rate: float = 20.0):
        super().__init__(app)
        self.capacity = capacity
        self.refill_rate = refill_rate

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        bucket_key = f"rate_limit:{client_ip}"

        bucket_data = await Cache.get(bucket_key)
        bucket = TokenBucket(self.capacity, self.refill_rate)

        if bucket_data:
            bucket.tokens = bucket_data["tokens"]
            bucket.last_refill = bucket_data["last_refill"]

        if not bucket.consume():
            return Response("Rate limit exceeded", status_code=429)

        await Cache.set(
            bucket_key,
            {"tokens": bucket.tokens, "last_refill": bucket.last_refill},
            ttl=60,
        )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))
        return response
