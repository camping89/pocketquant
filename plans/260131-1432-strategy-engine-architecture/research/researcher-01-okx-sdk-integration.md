# Python-OKX SDK Integration Research

**Date:** 2026-01-31 | **Focus:** OKX trading API for strategy engine

## Executive Summary

Two primary Python SDKs available: **okx-sdk** (burakoner, comprehensive) and **python-okx** (official unofficial). Both support REST and WebSocket APIs with full order management. Key constraint: **TP/SL cannot be attached to market orders** - only limit orders.

## SDK Comparison (UPDATED 2026-01-31)

| Aspect | python-okx ✅ | okx-sdk |
|--------|--------------|---------|
| **Downloads** | **1.3M** | 97K |
| **GitHub Stars** | **827** | 25 |
| **Contributors** | **11** | 1 |
| **Organization** | Module-based (`Account`, `Trade`, etc) | `OkxRestClient` + `OkxSocketClient` |
| **Python Version** | 3.7-3.12 | 3.9+ |
| **Latest Version** | **0.4.1** (Jan 2026) | 5.5.812 |
| **Recommendation** | **USE THIS** | Less community support |

## Authentication Setup

### okx-sdk Pattern
```python
from okx import OkxRestClient

# Live trading
api = OkxRestClient('API_KEY', 'API_SECRET', 'PASS_PHRASE')

# WebSocket with credentials
from okx import OkxSocketClient
ws = OkxSocketClient('API_KEY', 'API_SECRET', 'PASS_PHRASE')
```

### python-okx Pattern
```python
from okx import Account, Trade

account = Account.AccountAPI(
    api_key="your-key",
    api_secret_key="your-secret",
    passphrase="your-passphrase",
    flag="1"  # 0=live, 1=demo
)
```

## Order Placement

### Market Order (No TP/SL)
```python
# okx-sdk
order = api.trade.place_order(
    instId="BTC-USDT",      # Instrument ID
    tdMode="cash",          # cash/margin/isolated
    side="buy",
    orderType="market",
    sz="0.01"               # Amount in base currency
)

# python-okx
from okx import Trade
trade_api = Trade.TradeAPI(api_key, secret, passphrase, flag="1")
order = trade_api.place_order(
    instId="BTC-USDT",
    tdMode="cash",
    side="buy",
    ordType="market",
    sz="0.01"
)
```

### Limit Order (TP/SL Supported)
```python
# okx-sdk - with TP/SL
order = api.trade.place_order(
    instId="BTC-USDT",
    tdMode="cash",
    side="buy",
    orderType="limit",
    sz="0.01",
    px="40000",             # Price for limit order
    tpTriggerPx="45000",    # Take-profit trigger price
    tpOrdPx="45000",        # Take-profit order price (optional)
    slTriggerPx="35000",    # Stop-loss trigger price
    slOrdPx="35000"         # Stop-loss order price (optional)
)
```

**Critical Constraints:**
- TP/SL orders generated only when main order fills fully
- Cannot use TP/SL with market buy (target=base) or market sell (target=quote)
- Split TP/SL orders support only one-way directions

## WebSocket Private Channel

### Connection Setup
```python
from okx import OkxSocketClient

ws = OkxSocketClient(api_key, secret, passphrase)

# Private channel URLs:
# Live: wss://ws.okx.com:8443/ws/v5/private
# Demo: wss://ws.okx.com:8443/ws/v5/private?brokerId=9999
```

### Order Update Subscription
```python
# Subscribe to order updates for specific instrument
ws.private.subscribe_orders(
    instId="BTC-USDT",
    callback=on_order_update
)

def on_order_update(data):
    # Receives: ordId, state, fillSz, fillPx, etc.
    print(f"Order {data['ordId']}: {data['state']}")
```

### Expected Order States
- `pending` → `live` → `partially_filled` → `filled` or `canceled`
- WebSocket authenticates separately from REST (API key login only counts as one usage)

## Error Handling & Rate Limits

**OKX Rate Limits:**
- REST: Depends on VIP level (typically 10-100 requests/sec)
- WebSocket: Authenticated messages unlimited after login

**Standard Pattern:**
```python
from okx import exceptions

try:
    order = api.trade.place_order(...)
except exceptions.OkxAPIError as e:
    if e.code == "50000":  # System error
        # Retry with exponential backoff
        pass
    elif e.code == "58000":  # Rate limit
        # Wait and retry
        pass
```

## Module Structure Reference

**okx-sdk Available Modules:**
- `api.trade.*` - Order placement, cancellation, modification
- `api.account.*` - Balance, positions, leverage settings
- `api.market_data.*` - Tickers, orderbooks, trades history
- `api.algo_trading.*` - Conditional orders, trailing stops
- `ws.private.*` - Orders, balance, position updates
- `ws.public.*` - Tickers, orderbooks, mark prices

## Integration Recommendation

**Choose python-okx for strategy engine:**
- 13x more downloads, 33x more stars
- 11 contributors (active community)
- Maintained by okxapi organization
- Module-based design (`Trade.TradeAPI`, `Account.AccountAPI`)

**Implementation flow:**
1. REST for order placement (buy/sell signals)
2. WebSocket private for order status tracking
3. REST for position queries periodically
4. Algo orders for advanced TP/SL strategies (OCO orders available)

## Unresolved Questions

- Does okx-sdk handle order response parsing automatically or require manual mapping?
- Are there examples of graceful WebSocket reconnection with order state recovery?
- Performance impact of multiple concurrent WebSocket subscriptions?

---

**Sources:**
- [okx-sdk GitHub](https://github.com/burakoner/okx-sdk)
- [python-okx GitHub](https://github.com/okxapi/python-okx)
- [OKX API Documentation](https://my.okx.com/docs-v5/en/)
- [OKX V5 API Guide](https://www.okx.com/en-us/learn/complete-guide-to-okex-api-v5-upgrade)
