# Phase 04: OKX WebSocket Client

## Context Links

- Parent: [plan.md](./plan.md)
- Research: [researcher-01-okx-websocket-api.md](./research/researcher-01-okx-websocket-api.md)
- Existing: `src/infrastructure/brokers/okx/okx_broker.py` (placeholder `_ws_listener`)

## Overview

| Field | Value |
|-------|-------|
| Priority | P2 - High |
| Status | pending |
| Estimate | 3h |

WebSocket client for OKX private channels with HMAC-SHA256 authentication.

## Key Insights

1. **python-okx SDK** - Has WebSocket support, use it instead of raw websockets
2. **Private endpoint** - `wss://ws.okx.com:8443/ws/v5/private`
3. **Auth signature** - HMAC-SHA256 with timestamp + 'GET' + '/users/self/verify'
4. **30s TTL** - Signature expires 30 seconds after timestamp
5. **Demo vs Live** - Different flag ("1" = demo, "0" = live)

## Requirements

### Functional
- Connect to OKX private WebSocket
- Authenticate with HMAC-SHA256 signature
- Subscribe to `orders` channel (SWAP instrument type)
- Subscribe to `positions` channel (SWAP instrument type)
- Handle ping/pong keepalive
- Expose async iterator for messages

### Non-Functional
- Connection established within 5 seconds
- Auth signature valid for 30 seconds
- Heartbeat every 25 seconds (before 30s timeout)

## Architecture

```
OkxWebSocketClient
    │
    ├─ connect()
    │   ├─ Create WebSocket connection
    │   ├─ Generate HMAC-SHA256 signature
    │   ├─ Send login message
    │   └─ Wait for login response
    │
    ├─ subscribe(channels: list[str])
    │   ├─ Send subscribe message
    │   └─ Wait for confirmation
    │
    ├─ async for message in client:
    │   └─ Yield parsed messages
    │
    └─ disconnect()
        └─ Close WebSocket gracefully
```

### Authentication Flow

```python
import base64
import hmac
import hashlib
from datetime import datetime, UTC

def generate_signature(api_secret: str) -> tuple[str, str]:
    """Generate OKX WebSocket auth signature."""
    timestamp = str(int(datetime.now(UTC).timestamp()))
    pre_hash = timestamp + "GET" + "/users/self/verify"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), pre_hash.encode(), hashlib.sha256).digest()
    ).decode()
    return timestamp, signature

# Login message format
login_msg = {
    "op": "login",
    "args": [{
        "apiKey": api_key,
        "passphrase": passphrase,
        "timestamp": timestamp,
        "sign": signature
    }]
}
```

### Subscribe Message Format

```python
# Orders channel
subscribe_orders = {
    "op": "subscribe",
    "args": [{"channel": "orders", "instType": "SWAP"}]
}

# Positions channel
subscribe_positions = {
    "op": "subscribe",
    "args": [{"channel": "positions", "instType": "SWAP"}]
}
```

## Related Code Files

### Create
| File | Purpose | LOC |
|------|---------|-----|
| `src/infrastructure/brokers/okx/websocket/okx-websocket-client.py` | Main WS client | ~150 |
| `src/infrastructure/brokers/okx/websocket/okx-auth.py` | HMAC signature gen | ~40 |
| `src/infrastructure/brokers/okx/websocket/__init__.py` | Module exports | ~5 |

### Modify
| File | Change |
|------|--------|
| `src/infrastructure/brokers/okx/okx_broker.py` | Use OkxWebSocketClient in `_ws_listener` |

## Implementation Steps

1. **Create OkxAuth module**
   ```python
   # src/infrastructure/brokers/okx/websocket/okx-auth.py
   def generate_ws_signature(api_secret: str) -> tuple[str, str]:
       """Return (timestamp, signature) for WS login."""
       ...

   def build_login_message(api_key: str, passphrase: str, api_secret: str) -> dict:
       """Build complete login message."""
       ...
   ```

2. **Create OkxWebSocketClient**
   ```python
   class OkxWebSocketClient:
       def __init__(self, api_key: str, api_secret: str, passphrase: str, demo: bool = True):
           self._api_key = api_key
           self._api_secret = api_secret
           self._passphrase = passphrase
           self._demo = demo
           self._ws: WebSocketClientProtocol | None = None
           self._connected = False
           self._authenticated = False

       @property
       def ws_url(self) -> str:
           if self._demo:
               return "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
           return "wss://ws.okx.com:8443/ws/v5/private"

       async def connect(self) -> None:
           """Connect and authenticate."""
           ...

       async def subscribe(self, channels: list[dict]) -> None:
           """Subscribe to channels."""
           ...

       async def __aiter__(self):
           """Async iterator for messages."""
           while self._connected:
               msg = await self._ws.recv()
               yield json.loads(msg)

       async def disconnect(self) -> None:
           """Close connection."""
           ...
   ```

3. **Implement heartbeat**
   - Send "ping" every 25 seconds
   - Expect "pong" response
   - Reconnect if no pong within 5 seconds

4. **Update OkxBroker._ws_listener**
   ```python
   async def _ws_listener(self) -> None:
       client = OkxWebSocketClient(
           self._api_key, self._api_secret, self._passphrase, self._demo
       )
       await client.connect()
       await client.subscribe([
           {"channel": "orders", "instType": "SWAP"},
           {"channel": "positions", "instType": "SWAP"}
       ])

       async for message in client:
           # Pass to message parser (Phase 05)
           await self._handle_ws_message(message)
   ```

5. **Handle connection events**
   - Login success: `{"event": "login", "code": "0"}`
   - Subscribe success: `{"event": "subscribe", "arg": {...}}`
   - Error: `{"event": "error", "code": "...", "msg": "..."}`

## Todo List

- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-auth.py`
- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-websocket-client.py`
- [ ] Implement connect with auth
- [ ] Implement subscribe
- [ ] Implement async message iteration
- [ ] Implement heartbeat (ping/pong)
- [ ] Update OkxBroker to use new client
- [ ] Unit test: signature generation matches known vector
- [ ] Integration test: connect to demo endpoint

## Success Criteria

- [ ] Connects to OKX WebSocket within 5 seconds
- [ ] Auth signature accepted (login code "0")
- [ ] Subscribe to orders channel succeeds
- [ ] Subscribe to positions channel succeeds
- [ ] Messages received via async iterator
- [ ] Heartbeat keeps connection alive

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Signature rejected (clock skew) | Medium | High | Use NTP sync; log server time from error |
| Demo endpoint different from live | Low | Medium | Test both; document differences |
| Rate limit on subscribe (480/hour) | Low | Medium | Batch subscriptions; track count |

## Security Considerations

- API credentials from environment only
- Never log passphrase or secret
- Signature has 30s TTL (replay protection)
- Use secure WebSocket (wss://)

## Next Steps

After this phase:
- Phase 05: Parse order/position messages and trigger callbacks
