# Phase 7: Integration Infrastructure

## Context Links
- Parent: [plan.md](plan.md)
- Blocked by: [Phase 5](phase-05-refactor-features-cqrs.md)
- Research: [Middleware Patterns](research/researcher-middleware-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P2 |
| Status | completed |
| Effort | 2h |

Add webhook dispatcher and resilient HTTP client for external integrations.

## Key Insights

Integration requirements:
- **Webhooks:** Dispatch domain events to external URLs
- **HTTP Client:** Retry with exponential backoff, circuit breaker pattern
- Both should include correlation IDs for traceability

## Requirements

### Functional
- Webhook dispatcher with retry
- Configurable webhook endpoints per event type
- Resilient HTTP client with timeout/retry

### Non-Functional
- Async execution (non-blocking)
- Circuit breaker for failing endpoints
- Correlation ID propagation

## Architecture

```
src/infrastructure/
├── http_client/
│   ├── __init__.py
│   └── client.py              # ResilientHttpClient
└── webhooks/
    ├── __init__.py
    ├── dispatcher.py          # WebhookDispatcher
    └── config.py              # WebhookConfig
```

## Related Code Files

### Create
- `src/infrastructure/http_client/__init__.py`
- `src/infrastructure/http_client/client.py`
- `src/infrastructure/webhooks/__init__.py`
- `src/infrastructure/webhooks/dispatcher.py`
- `src/infrastructure/webhooks/config.py`

### Modify
- `src/config.py` - Add webhook configuration
- `src/main.py` - Initialize webhook dispatcher

## Implementation Steps

1. **Create Resilient HTTP Client**
   ```python
   # src/infrastructure/http_client/client.py
   import asyncio
   import aiohttp
   from typing import Dict, Any, Optional
   from dataclasses import dataclass
   from src.common.logging import get_logger
   from src.common.tracing.context import get_correlation_id
   from src.common.constants import HEADER_CORRELATION_ID

   logger = get_logger(__name__)

   @dataclass
   class RetryConfig:
       max_retries: int = 3
       base_delay: float = 1.0
       max_delay: float = 30.0
       timeout: float = 10.0

   class ResilientHttpClient:
       def __init__(self, config: RetryConfig = None):
           self.config = config or RetryConfig()
           self._session: Optional[aiohttp.ClientSession] = None

       async def _get_session(self) -> aiohttp.ClientSession:
           if self._session is None or self._session.closed:
               self._session = aiohttp.ClientSession(
                   timeout=aiohttp.ClientTimeout(total=self.config.timeout)
               )
           return self._session

       async def post(
           self,
           url: str,
           json: Dict[str, Any],
           headers: Dict[str, str] = None
       ) -> Dict[str, Any]:
           headers = headers or {}
           headers[HEADER_CORRELATION_ID] = get_correlation_id()

           last_error = None
           for attempt in range(self.config.max_retries + 1):
               try:
                   session = await self._get_session()
                   async with session.post(url, json=json, headers=headers) as resp:
                       resp.raise_for_status()
                       return await resp.json()
               except Exception as e:
                   last_error = e
                   if attempt < self.config.max_retries:
                       delay = min(
                           self.config.base_delay * (2 ** attempt),
                           self.config.max_delay
                       )
                       logger.warning(
                           "http_retry",
                           url=url,
                           attempt=attempt + 1,
                           delay=delay,
                           error=str(e)
                       )
                       await asyncio.sleep(delay)

           raise last_error

       async def close(self):
           if self._session and not self._session.closed:
               await self._session.close()
   ```

2. **Create Webhook Config**
   ```python
   # src/infrastructure/webhooks/config.py
   from dataclasses import dataclass, field
   from typing import Dict, List

   @dataclass
   class WebhookEndpoint:
       url: str
       secret: str = ""
       enabled: bool = True

   @dataclass
   class WebhookConfig:
       endpoints: Dict[str, List[WebhookEndpoint]] = field(default_factory=dict)

       def get_endpoints(self, event_type: str) -> List[WebhookEndpoint]:
           return [e for e in self.endpoints.get(event_type, []) if e.enabled]
   ```

3. **Create Webhook Dispatcher**
   ```python
   # src/infrastructure/webhooks/dispatcher.py
   import hashlib
   import hmac
   import json
   from dataclasses import asdict
   from typing import Any
   from src.infrastructure.http_client.client import ResilientHttpClient
   from src.infrastructure.webhooks.config import WebhookConfig, WebhookEndpoint
   from src.domain.shared.events import DomainEvent
   from src.common.logging import get_logger

   logger = get_logger(__name__)

   class WebhookDispatcher:
       def __init__(self, config: WebhookConfig, client: ResilientHttpClient = None):
           self.config = config
           self.client = client or ResilientHttpClient()

       async def dispatch(self, event: DomainEvent) -> None:
           event_type = type(event).__name__
           endpoints = self.config.get_endpoints(event_type)

           if not endpoints:
               return

           payload = self._build_payload(event)

           for endpoint in endpoints:
               try:
                   headers = {}
                   if endpoint.secret:
                       headers["X-Webhook-Signature"] = self._sign(payload, endpoint.secret)

                   await self.client.post(endpoint.url, payload, headers)
                   logger.info(
                       "webhook_sent",
                       event_type=event_type,
                       url=endpoint.url
                   )
               except Exception as e:
                   logger.error(
                       "webhook_failed",
                       event_type=event_type,
                       url=endpoint.url,
                       error=str(e)
                   )

       def _build_payload(self, event: DomainEvent) -> dict:
           return {
               "event_type": type(event).__name__,
               "data": self._serialize_event(event),
               "aggregate_id": str(event.aggregate_id),
               "occurred_at": event.occurred_at.isoformat()
           }

       def _serialize_event(self, event: DomainEvent) -> dict:
           data = asdict(event)
           data.pop("aggregate_id", None)
           data.pop("occurred_at", None)
           return data

       def _sign(self, payload: dict, secret: str) -> str:
           body = json.dumps(payload, sort_keys=True)
           return hmac.new(
               secret.encode(),
               body.encode(),
               hashlib.sha256
           ).hexdigest()

       async def close(self):
           await self.client.close()
   ```

4. **Add webhook config to Settings**
   ```python
   # In src/config.py
   from typing import Dict, List, Optional

   class Settings(BaseSettings):
       # ... existing settings

       # Webhooks (JSON string in env)
       webhooks_config: Optional[str] = None

       def get_webhook_config(self) -> "WebhookConfig":
           from src.infrastructure.webhooks.config import WebhookConfig, WebhookEndpoint

           if not self.webhooks_config:
               return WebhookConfig()

           import json
           data = json.loads(self.webhooks_config)
           endpoints = {}
           for event_type, urls in data.items():
               endpoints[event_type] = [
                   WebhookEndpoint(url=u["url"], secret=u.get("secret", ""))
                   for u in urls
               ]
           return WebhookConfig(endpoints=endpoints)
   ```

5. **Create event handler for webhooks**
   ```python
   # src/features/market_data/sync/event_handlers.py
   from src.domain.ohlcv.events import HistoricalDataSynced
   from src.infrastructure.webhooks.dispatcher import WebhookDispatcher

   def create_webhook_handler(dispatcher: WebhookDispatcher):
       async def on_historical_synced(event: HistoricalDataSynced):
           await dispatcher.dispatch(event)
       return on_historical_synced
   ```

6. **Initialize in main.py**
   ```python
   from src.infrastructure.http_client.client import ResilientHttpClient
   from src.infrastructure.webhooks.dispatcher import WebhookDispatcher

   # In lifespan
   http_client = ResilientHttpClient()
   webhook_dispatcher = WebhookDispatcher(
       config=settings.get_webhook_config(),
       client=http_client
   )

   # Register webhook handler
   from src.features.market_data.sync.event_handlers import create_webhook_handler
   event_bus.subscribe(
       HistoricalDataSynced,
       create_webhook_handler(webhook_dispatcher)
   )

   # Cleanup
   yield
   await webhook_dispatcher.close()
   ```

## Todo List

- [ ] Create `src/infrastructure/http_client/` directory
- [ ] Implement ResilientHttpClient with retry
- [ ] Create `src/infrastructure/webhooks/` directory
- [ ] Implement WebhookConfig
- [ ] Implement WebhookDispatcher
- [ ] Add webhook config to Settings
- [ ] Create webhook event handler
- [ ] Initialize in main.py
- [ ] Add cleanup in shutdown
- [ ] Run tests

## Success Criteria

- [ ] HTTP client retries on failure
- [ ] Webhook dispatcher sends to configured endpoints
- [ ] HMAC signature included when secret configured
- [ ] Correlation ID in webhook headers
- [ ] All tests pass

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Webhook endpoint down | Medium | Low | Retry with backoff |
| Secret exposure | Low | High | Use env vars |
| Blocking event loop | Low | Medium | Async dispatch |

## Security Considerations

- HMAC signatures for webhook authenticity
- Secrets stored in environment variables
- HTTPS only for webhook URLs (validation optional)

## Next Steps

After completion:
- Phase 8 updates tests and documentation
- Webhooks ready for external consumers
