# OKX WebSocket API v5 Private Channels Research
**Date:** 2026-01-31 | **Scope:** Trading integration for PocketQuant

## 1. Authentication Flow (HMAC-SHA256)

### Sign Generation Process
```
pre_hash_string = timestamp + 'GET' + '/users/self/verify'
signature = Base64(HMAC-SHA256(pre_hash_string, secret_key))
```

**Critical Details:**
- Timestamp: UTC Unix timestamp (seconds)
- Request expires 30 seconds after timestamp
- All credentials required: API Key, Secret Key, Passphrase
- Signature must be Base64-encoded

### Python Implementation (python-okx SDK)
```python
import os
import hmac
import hashlib
import base64
from datetime import datetime

api_key = os.getenv('OKX_API_KEY')
api_secret = os.getenv('OKX_API_SECRET')
passphrase = os.getenv('OKX_PASSPHRASE')

timestamp = str(int(datetime.utcnow().timestamp()))
pre_hash = timestamp + 'GET' + '/users/self/verify'
signature = base64.b64encode(
    hmac.new(api_secret.encode(), pre_hash.encode(), hashlib.sha256).digest()
).decode()

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

## 2. Orders Channel Message Format & State Transitions

### Subscription
```json
{
  "op": "subscribe",
  "args": [
    {"channel": "orders", "instType": "SWAP"}
  ]
}
```

### Message Structure (Snapshot + Update Pattern)
```json
{
  "arg": {"channel": "orders", "instType": "SWAP"},
  "data": [{
    "instId": "BTC-USD-SWAP",
    "ordId": "123456789",
    "clOrdId": "client-order-id",
    "state": "live",
    "px": "45000.5",
    "sz": "1",
    "accFillSz": "0",
    "avgPx": "0",
    "tradeId": "",
    "fillPx": "",
    "fillTime": "",
    "fillSz": "0",
    "pnl": "0",
    "pnlRatio": "0",
    "ctType": "linear",
    "instType": "SWAP",
    "tpTriggerPx": "",
    "slTriggerPx": "",
    "ordType": "limit",
    "side": "buy",
    "posSide": "long",
    "tdMode": "cross",
    "ccy": "",
    "uTime": "1234567890",
    "execType": ""
  }],
  "ts": "1234567890000"
}
```

### Order State Lifecycle
| State | Meaning | Terminal |
|-------|---------|----------|
| `live` | Order placed, awaiting execution | No |
| `partially_filled` | Partial fill received | No |
| `filled` | Fully executed | **Yes** |
| `canceled` | User-cancelled or system-cancelled | **Yes** |
| `mmp_canceled` | Market-maker protection triggered | **Yes** |

**Key Rules:**
- Process only the FIRST `filled` message per ordId (discard duplicates)
- Process only the FIRST `canceled` message per ordId
- Order transitions: `live` → `partially_filled` → `filled` OR `live` → `canceled`
- IOC orders may transition: `live` → `partially_filled` → `canceled`
- Terminal states: `filled`, `canceled`, `mmp_canceled`
- Use `tradeId` for reconciliation with positions channel

## 3. Positions Channel Message Format

### Subscription
```json
{
  "op": "subscribe",
  "args": [
    {"channel": "positions", "instType": "SWAP"}
  ]
}
```

### Message Structure
```json
{
  "arg": {"channel": "positions", "instType": "SWAP"},
  "data": [{
    "posId": "3091d0e0-8d77-42fa-b4a8-90a1f1f5c03f",
    "instId": "BTC-USD-SWAP",
    "instType": "SWAP",
    "mgnMode": "cross",
    "posSide": "long",
    "pos": "10",
    "baseBal": "0",
    "quoteBal": "0",
    "posCcy": "BTC",
    "avlPos": "10",
    "avgPx": "44000",
    "markPx": "45000.5",
    "upl": "15000",
    "uplRatio": "0.0341",
    "lever": "5",
    "liquidationPx": "35000",
    "mmr": "0.02",
    "imr": "0.1",
    "margin": "90000",
    "mgnRatio": "0.5",
    "optVal": "0",
    "notionalUsd": "450005",
    "adl": "1",
    "ccy": "USD",
    "deltaBS": "0",
    "deltaPA": "0",
    "deltaTheta": "0",
    "tradeId": "123456789",
    "uTime": "1234567890000"
  }],
  "ts": "1234567890000"
}
```

### Key Fields
- **posId**: Unique position identifier (generated from mgnMode + posSide + instId + ccy)
- **pos**: Position size (>0 = long, <0 = short)
- **posSide**: "long" or "short"
- **tradeId**: Latest trade ID associated with this position (matches orders channel)
- **Initial Snapshot**: Published only for non-zero positions (pos ≠ 0)
- **Subsequent Updates**: Driven by order fills and position modifications

## 4. Sequence ID & Guaranteed Delivery

### OKX Approach
OKX does **NOT** use explicit sequence IDs for private channels like some exchanges. Instead:
- Each message includes a `ts` (timestamp in milliseconds)
- Client should maintain `uTime` for positions and orders
- Reconciliation relies on **tradeId matching** between orders and positions

### Reconnection Strategy
1. **Subscribe to positions**: Receive snapshot of all non-zero positions
2. **Subscribe to orders**: Receive current active orders
3. **Detect gaps**: Compare local state with snapshot after reconnection
4. **Resync**: Use REST API to fetch missed state if needed

### Code Pattern
```python
# After reconnection
async def resync_state():
    # 1. Get current positions via REST
    positions = await rest_api.get_positions()

    # 2. Get pending orders via REST
    orders = await rest_api.get_orders(state='open')

    # 3. Validate against WebSocket snapshots
    # 4. Process any missed fills
```

## 5. Reconnection Best Practices

### Automatic Reconnection
**python-okx SDK** provides:
- Built-in reconnection with exponential backoff
- Multiplexed connections support
- Automatic resubscription to channels

### Manual Implementation Checklist
1. **Connection loss detection**: Monitor ping/pong frames (30s timeout)
2. **Exponential backoff**: 1s → 2s → 4s → 8s (max 60s)
3. **Resubscription order**: Login → Public channels → Private channels
4. **State reconciliation**: Always fetch REST snapshot after reconnection
5. **Message buffering**: Store messages during reconnection phase
6. **Idempotency**: Use ordId/posId to prevent duplicates

### Channels Persistence
- **Orders**: Maintained across reconnects (REST fallback available)
- **Positions**: Snapshot sent on each connection (compare hashes)
- **Rate limits**: 480 subscribe/unsubscribe per hour

## 6. Python-okx SDK Usage

### Basic WebSocket Setup
```python
from okx.websocket import WsPrivateClient

# Initialize
ws = WsPrivateClient(
    api_key="YOUR_KEY",
    api_secret="YOUR_SECRET",
    passphrase="YOUR_PASSPHRASE",
    use_live=True,  # False for testnet
)

# Subscribe to channels
ws.orders_channel("SWAP")
ws.positions_channel("SWAP")

# Handle messages
async def on_message(message):
    if message['arg']['channel'] == 'orders':
        handle_order_update(message['data'])
    elif message['arg']['channel'] == 'positions':
        handle_position_update(message['data'])

ws.add_listener(on_message)

# Start connection
await ws.connect()
```

### Automatic Reconnection
```python
# SDK handles reconnection automatically
# Configuration (if available in SDK):
# - Max retries: typically unlimited
# - Backoff: exponential (typically 1-60 seconds)
# - Resubscription: automatic on reconnect
```

## Key Takeaways

1. **Auth**: HMAC-SHA256 with 30s TTL - renew on each session
2. **Orders**: Track state transitions (live → filled/canceled)
3. **Positions**: Initial snapshot + event-driven updates
4. **Delivery**: Use tradeId for reconciliation, not sequence IDs
5. **Reconnection**: Implement REST fallback for critical data
6. **SDK**: python-okx provides battle-tested reconnection handling

## Unresolved Questions

- Exact timestamp format for WebSocket ping/pong (ISO vs Unix)?
- Maximum message queue size during reconnection phase?
- Rate limit headers in WebSocket subscribe responses?

---

**Sources:**
- [OKX API Documentation](https://www.okx.com/docs-v5/en/)
- [python-okx Repository](https://github.com/okxapi/python-okx)
- [okx-sdk Documentation](https://github.com/burakoner/okx-sdk)
