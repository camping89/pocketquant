# FastAPI Cross-Cutting Middleware Patterns for Production

## 1. Correlation ID Middleware with ContextVars

**Pattern**: Use Python's `contextvars` for async-safe context propagation. ContextVar preserves context per async execution chain, preventing concurrent request interference.

```python
# src/common/middleware/correlation_id.py
import contextvars
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_contextvar = contextvars.ContextVar('request_id', default=None)

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        token = request_id_contextvar.set(request_id)

        try:
            response = await call_next(request)
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            request_id_contextvar.reset(token)  # Critical: prevent context leakage
```

**Logging Integration**: Structlog filter reads ContextVar and injects into all logs:
```python
def correlation_id_filter(logger, method_name, event_dict):
    event_dict['request_id'] = request_id_contextvar.get()
    return event_dict

structlog.configure(processors=[correlation_id_filter, ...])
```

**Key Insight**: Always capture and reset tokens to prevent leakage in thread pools. Background tasks need explicit context copying since they execute after middleware completion.

## 2. Idempotency Middleware - Redis-Backed

**Pattern**: Cache POST/PATCH request bodies + responses with idempotency keys. Replay responses on duplicate requests.

```python
# src/common/middleware/idempotency.py
import hashlib
from starlette.middleware.base import BaseHTTPMiddleware

class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in ['POST', 'PATCH']:
            return await call_next(request)

        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return await call_next(request)

        cache_key = f'idempotent:{idempotency_key}'
        cached = await Cache.get(cache_key)
        if cached:
            return Response(content=cached['body'],
                          status_code=cached['status'],
                          headers=cached['headers'])

        body = await request.body()
        response = await call_next(request)
        response_body = b''
        async for chunk in response.body_iterator:
            response_body += chunk

        await Cache.set(cache_key, {
            'body': response_body,
            'status': response.status_code,
            'headers': dict(response.headers)
        }, ttl=86400)  # 24h retention

        return StreamingResponse(iter([response_body]),
                                status_code=response.status_code)
```

**Best Practice**: Use atomic Redis operations (`SET ... NX`) to prevent race conditions. Scope keys per client if needed.

## 3. Rate Limiting - Token Bucket Algorithm

**Pattern**: Simple, predictable token bucket with Redis backing for distributed systems.

```python
# src/common/middleware/rate_limit.py
import time
from starlette.middleware.base import BaseHTTPMiddleware

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = capacity
        self.last_refill = time.time()

    async def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity,
                         self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_id = request.client.host
        bucket_key = f'rate_limit:{client_id}'

        # Use Redis for distributed setup
        bucket_data = await Cache.get(bucket_key)
        bucket = TokenBucket(capacity=100, refill_rate=10)  # 100 req/10s

        if bucket_data:
            bucket.tokens = bucket_data['tokens']
            bucket.last_refill = bucket_data['last_refill']

        if not await bucket.consume():
            return Response('Rate limit exceeded', status_code=429)

        await Cache.set(bucket_key, {
            'tokens': bucket.tokens,
            'last_refill': bucket.last_refill
        }, ttl=60)

        response = await call_next(request)
        response.headers['X-RateLimit-Remaining'] = str(int(bucket.tokens))
        return response
```

**Gotcha**: Token bucket allows bursts (design feature). For strict limits, use sliding window instead.

## 4. Health Check Aggregation

**Pattern**: Parallel check execution with timeouts. Return overall status + per-dependency details.

```python
# src/features/system/api/health_routes.py
import asyncio
from typing import Any

async def check_database() -> dict[str, Any]:
    try:
        await asyncio.wait_for(Database.health_check(), timeout=5)
        return {'status': 'healthy', 'latency_ms': 15}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}

async def check_redis() -> dict[str, Any]:
    try:
        await asyncio.wait_for(Cache.ping(), timeout=5)
        return {'status': 'healthy', 'latency_ms': 8}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}

@app.get('/health')
async def health_check() -> dict[str, Any]:
    results = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=False
    )

    db_status, cache_status = results
    overall = 'healthy' if all(
        r.get('status') == 'healthy' for r in results
    ) else 'unhealthy'

    return {
        'status': overall,
        'dependencies': {
            'database': db_status,
            'cache': cache_status
        }
    }
```

**Pattern Benefits**: Parallel execution scales to many dependencies. Timeouts prevent hanging checks from blocking the health endpoint.

## 5. Middleware Ordering Best Practices

**Execution Model** ("Onion" pattern):
```
Request:  Outer (Last Added) → Inner (First Added) → Route Handler
Response: Inner (First Added) → Outer (Last Added)
```

**Recommended Order** (from outermost to innermost):
1. **Error Handling** - Catch all exceptions, return proper status codes
2. **Correlation ID** - Must be early to track all operations
3. **CORS** - Security boundary check
4. **Rate Limiting** - Reject excess traffic before processing
5. **Idempotency** - Deduplicate requests before business logic
6. **Request Logging** - Log after validation layers

**Configuration Example**:
```python
def create_app() -> FastAPI:
    app = FastAPI()

    # Order matters: add in reverse (last added = outermost)
    app.add_middleware(CORSMiddleware, ...)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    return app
```

**Critical Insight**: If middleware depends on dependencies with `yield`, cleanup runs AFTER all middleware exit. Background tasks run after middleware, so context propagation requires explicit copying.

## Key Takeaways

- **ContextVars**: Always reset tokens to prevent leakage; thread-safe for async code
- **Idempotency**: Use 24h TTL; atomic Redis ops prevent race conditions
- **Rate Limiting**: Token bucket simple but allows bursts; sliding window for strict limits
- **Health Checks**: Parallel with timeouts (5-10s each); include per-dependency details
- **Middleware Order**: Think "onion layers" - outer runs first on request, last on response

## Implementation Priority for PocketQuant

1. **Correlation ID** (enables observability across logs)
2. **Health Check Aggregation** (production requirement)
3. **Rate Limiting** (protect API from abuse)
4. **Idempotency** (critical for financial data requests)

## Sources

- [Setting up request ID logging for FastAPI](https://medium.com/@sondrelg_12432/setting-up-request-id-logging-for-your-fastapi-application-4dc190aac0ea)
- [Correlation ID middleware discussion](https://github.com/fastapi/fastapi/discussions/8190)
- [asgi-idempotency-header library](https://github.com/snok/asgi-idempotency-header)
- [FastAPI rate limiting with token buckets](https://blog.compliiant.io/api-defense-with-rate-limiting-using-fastapi-and-token-buckets-0f5206fc5029)
- [FastAPI health check library](https://github.com/Kludex/fastapi-health)
- [Middleware ordering best practices](https://medium.com/@dynamicy/fastapi-starlette-lifecycle-guide-startup-order-pitfalls-best-practices-and-a-production-ready-53e29dcb9249)
- [FastAPI middleware documentation](https://fastapi.tiangolo.com/tutorial/middleware/)
