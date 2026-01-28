# Phase 6: Cross-Cutting Middleware

## Context Links
- Parent: [plan.md](plan.md)
- Blocked by: [Phase 5](phase-05-refactor-features-cqrs.md)
- Research: [Middleware Patterns](research/researcher-middleware-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 2h |

Add cross-cutting concerns: Correlation ID, Health Checks, Idempotency, Rate Limiting.

## Key Insights

From middleware research:
- **Correlation ID:** ContextVars for async-safe propagation
- **Health Checks:** Parallel execution with timeouts
- **Idempotency:** Redis-backed response caching
- **Rate Limiting:** Token bucket algorithm

Middleware order (onion model, outer→inner):
1. Error Handling (default)
2. Correlation ID
3. Rate Limiting
4. Idempotency
5. Request Logging

## Requirements

### Functional
- Correlation ID in all logs and response headers
- Health endpoint shows all dependencies
- POST/PATCH requests can be idempotent
- Rate limiting per client IP

### Non-Functional
- ContextVars for async safety
- 5-10s timeout per health check
- 24h idempotency key retention
- Token bucket with burst support

## Architecture

```
src/common/
├── tracing/
│   ├── __init__.py
│   ├── correlation.py          # CorrelationIDMiddleware
│   └── context.py              # request_id_contextvar
├── health/
│   ├── __init__.py
│   ├── coordinator.py          # HealthCoordinator
│   └── checks.py               # check_database, check_redis
├── idempotency/
│   ├── __init__.py
│   └── middleware.py           # IdempotencyMiddleware
└── rate_limit/
    ├── __init__.py
    └── middleware.py           # RateLimitMiddleware, TokenBucket
```

## Related Code Files

### Create
- `src/common/tracing/__init__.py`
- `src/common/tracing/correlation.py`
- `src/common/tracing/context.py`
- `src/common/health/__init__.py`
- `src/common/health/coordinator.py`
- `src/common/health/checks.py`
- `src/common/idempotency/__init__.py`
- `src/common/idempotency/middleware.py`
- `src/common/rate_limit/__init__.py`
- `src/common/rate_limit/middleware.py`

### Modify
- `src/main.py` - Register middleware
- `src/common/logging/setup.py` - Add correlation ID processor

## Implementation Steps

1. **Create Correlation ID context**
   ```python
   # src/common/tracing/context.py
   import contextvars
   from uuid import uuid4

   request_id_contextvar = contextvars.ContextVar("request_id", default=None)

   def get_correlation_id() -> str:
       return request_id_contextvar.get() or str(uuid4())

   def set_correlation_id(request_id: str) -> contextvars.Token:
       return request_id_contextvar.set(request_id)
   ```

2. **Create Correlation ID middleware**
   ```python
   # src/common/tracing/correlation.py
   from starlette.middleware.base import BaseHTTPMiddleware
   from starlette.requests import Request
   from starlette.responses import Response
   from uuid import uuid4
   from src.common.tracing.context import request_id_contextvar
   from src.common.constants import HEADER_CORRELATION_ID

   class CorrelationIDMiddleware(BaseHTTPMiddleware):
       async def dispatch(self, request: Request, call_next) -> Response:
           request_id = request.headers.get(HEADER_CORRELATION_ID) or str(uuid4())
           token = request_id_contextvar.set(request_id)

           try:
               response = await call_next(request)
               response.headers[HEADER_CORRELATION_ID] = request_id
               return response
           finally:
               request_id_contextvar.reset(token)
   ```

3. **Update structlog to include correlation ID**
   ```python
   # In src/common/logging/setup.py
   from src.common.tracing.context import get_correlation_id

   def add_correlation_id(logger, method_name, event_dict):
       event_dict["correlation_id"] = get_correlation_id()
       return event_dict

   # Add to processors list
   processors = [
       add_correlation_id,
       # ... existing processors
   ]
   ```

4. **Create Health Coordinator**
   ```python
   # src/common/health/coordinator.py
   import asyncio
   from typing import Dict, Any, Callable, List

   class HealthCoordinator:
       def __init__(self):
           self._checks: Dict[str, Callable] = {}
           self._timeout: float = 5.0

       def register(self, name: str, check_fn: Callable) -> None:
           self._checks[name] = check_fn

       async def check_all(self) -> Dict[str, Any]:
           results = await asyncio.gather(
               *[self._run_check(name, fn) for name, fn in self._checks.items()],
               return_exceptions=False
           )

           dependencies = dict(zip(self._checks.keys(), results))
           overall = "healthy" if all(
               r.get("status") == "healthy" for r in dependencies.values()
           ) else "unhealthy"

           return {"status": overall, "dependencies": dependencies}

       async def _run_check(self, name: str, fn: Callable) -> Dict[str, Any]:
           try:
               result = await asyncio.wait_for(fn(), timeout=self._timeout)
               return {"status": "healthy", **result}
           except asyncio.TimeoutError:
               return {"status": "unhealthy", "error": "timeout"}
           except Exception as e:
               return {"status": "unhealthy", "error": str(e)}
   ```

5. **Create health check functions**
   ```python
   # src/common/health/checks.py
   import time
   from src.infrastructure.persistence import Database, Cache

   async def check_database() -> dict:
       start = time.time()
       await Database.health_check()
       return {"latency_ms": int((time.time() - start) * 1000)}

   async def check_redis() -> dict:
       start = time.time()
       await Cache.ping()
       return {"latency_ms": int((time.time() - start) * 1000)}
   ```

6. **Create Idempotency middleware**
   ```python
   # src/common/idempotency/middleware.py
   from starlette.middleware.base import BaseHTTPMiddleware
   from starlette.requests import Request
   from starlette.responses import Response, StreamingResponse
   from src.infrastructure.persistence import Cache
   from src.common.constants import HEADER_IDEMPOTENCY_KEY

   class IdempotencyMiddleware(BaseHTTPMiddleware):
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
                   headers=cached["headers"]
               )

           response = await call_next(request)
           response_body = b""
           async for chunk in response.body_iterator:
               response_body += chunk

           await Cache.set(cache_key, {
               "body": response_body.decode(),
               "status": response.status_code,
               "headers": dict(response.headers)
           }, ttl=self.TTL)

           return Response(
               content=response_body,
               status_code=response.status_code,
               headers=dict(response.headers)
           )
   ```

7. **Create Rate Limit middleware**
   ```python
   # src/common/rate_limit/middleware.py
   import time
   from starlette.middleware.base import BaseHTTPMiddleware
   from starlette.requests import Request
   from starlette.responses import Response
   from src.infrastructure.persistence import Cache

   class TokenBucket:
       def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
           self.capacity = capacity
           self.refill_rate = refill_rate
           self.tokens = capacity
           self.last_refill = time.time()

       def consume(self, tokens: int = 1) -> bool:
           now = time.time()
           elapsed = now - self.last_refill
           self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
           self.last_refill = now

           if self.tokens >= tokens:
               self.tokens -= tokens
               return True
           return False

   class RateLimitMiddleware(BaseHTTPMiddleware):
       def __init__(self, app, capacity: int = 200, refill_rate: float = 20.0):
           super().__init__(app)
           self.capacity = capacity
           self.refill_rate = refill_rate

       async def dispatch(self, request: Request, call_next) -> Response:
           client_ip = request.client.host
           bucket_key = f"rate_limit:{client_ip}"

           bucket_data = await Cache.get(bucket_key)
           bucket = TokenBucket(self.capacity, self.refill_rate)

           if bucket_data:
               bucket.tokens = bucket_data["tokens"]
               bucket.last_refill = bucket_data["last_refill"]

           if not bucket.consume():
               return Response("Rate limit exceeded", status_code=429)

           await Cache.set(bucket_key, {
               "tokens": bucket.tokens,
               "last_refill": bucket.last_refill
           }, ttl=60)

           response = await call_next(request)
           response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))
           return response
   ```

8. **Register middleware in main.py**
   ```python
   # Order matters: outer middleware added last
   from src.common.tracing.correlation import CorrelationIDMiddleware
   from src.common.idempotency.middleware import IdempotencyMiddleware
   from src.common.rate_limit.middleware import RateLimitMiddleware

   app.add_middleware(RateLimitMiddleware, capacity=200, refill_rate=20)
   app.add_middleware(IdempotencyMiddleware)
   app.add_middleware(CorrelationIDMiddleware)
   ```

9. **Update health endpoint**
   ```python
   from src.common.health.coordinator import HealthCoordinator
   from src.common.health.checks import check_database, check_redis

   health_coordinator = HealthCoordinator()
   health_coordinator.register("database", check_database)
   health_coordinator.register("redis", check_redis)

   @app.get("/health")
   async def health():
       return await health_coordinator.check_all()
   ```

## Todo List

- [ ] Create `src/common/tracing/` directory
- [ ] Implement CorrelationIDMiddleware
- [ ] Update structlog processors
- [ ] Create `src/common/health/` directory
- [ ] Implement HealthCoordinator
- [ ] Create health check functions
- [ ] Create `src/common/idempotency/` directory
- [ ] Implement IdempotencyMiddleware
- [ ] Create `src/common/rate_limit/` directory
- [ ] Implement RateLimitMiddleware
- [ ] Register middleware in main.py
- [ ] Update health endpoint
- [ ] Run tests

## Success Criteria

- [ ] All logs include correlation_id
- [ ] X-Correlation-ID header in responses
- [ ] Health endpoint shows DB + Redis status
- [ ] POST with Idempotency-Key returns cached response
- [ ] Rate limiting returns 429 when exceeded
- [ ] All tests pass

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Context leak | Low | High | Always reset token in finally |
| Cache miss | Low | Low | Graceful fallback |
| Rate limit too strict | Medium | Low | Configurable parameters |

## Security Considerations

- Rate limiting prevents DoS
- Idempotency prevents duplicate operations
- Correlation IDs enable audit trails

## Next Steps

After completion:
- Phase 7 adds integration infrastructure
- Correlation IDs will propagate to webhooks
