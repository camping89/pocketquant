# WebSocket Architecture

**Scope:** Real-time architecture: outbound WebSocket ingest (Binance quotes, OKX orders) + SSE server-to-client egress (bars, quotes).

---

## Overview

Real-time architecture integrates **inbound WebSocket data sources** with **outbound Server-Sent Events (SSE) streams** for frontend clients:

**Inbound (WebSocket):**
1. **Binance `@aggTrade` stream** — singleton, app-wide, ingests market-data ticks.
2. **OKX private channels** — per-broker instance, ingests order/position updates.

**Outbound (SSE):**
- **Bars stream** — GET `/api/v1/market-data/bars/stream/{symbol}?interval={interval}`. Polls Redis for current bar, emits on change.
- **Quotes stream** — GET `/api/v1/quotes/stream/{symbol}`. Polls Redis for latest quote, emits on change.

**Data Bridge:** Redis acts as intermediary — inbound WS writes, SSE polls and emits to frontend.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     PocketQuant FastAPI app                                  │
│                                                                              │
│  ┌────────────────────────────────┐        ┌──────────────────────────────┐ │
│  │ Inbound WebSocket Clients       │        │ Outbound SSE Handlers        │ │
│  │                                 │        │                              │ │
│  │  • BinanceWebSocketClient       │        │  • /bars/stream/{symbol}     │ │
│  │    (singleton, @aggTrade)       │        │  • /quotes/stream/{symbol}   │ │
│  │                                 │        │                              │ │
│  │  • OkxWebSocketClient           │        │  Consumers (EventSource):     │ │
│  │    (per-broker, orders/pos)     │        │  • use-realtime-bar.ts       │ │
│  └─────────────┬──────────────────┘        │  • use-realtime-quote.ts     │ │
│                │                           └──────────────────┬───────────┘ │
│                │                                              │              │
│                ▼                                              ▼              │
│          ┌─────────────────┐                       ┌──────────────────┐    │
│          │  Redis Cache    │◄──────────────────────┤  SSE Poll Loop   │    │
│          │                 │   (1.0s bars,         │  (poll ≈ 0.5-1s) │    │
│          │ • bar:current   │    0.5s quotes)       │                  │    │
│          │ • quote:latest  │                       └──────────────────┘    │
│          └─────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────────────┘
       ▲                                                       ▼
       │                                            ┌────────────────────────┐
       └────────────────────────────────────────────┤ Frontend EventSource   │
                (upstream)                          │  • WebSocket fallback  │
                                                    │  • Auto-retry on close │
                                                    └────────────────────────┘
                                                               ▲
                                                         Browser
                                                      (pocketquant-web)
```

Frontend uses SSE push for live bars (1s cadence) and quotes (500ms cadence) with staleness detection and automatic fallback to REST if the SSE connection fails.

---

## A. Market-Data Stream (Binance)

### Files

| Path | Role |
|---|---|
| `src/pocketquant/core/infra/binance/binance_websocket_client.py:33` | `BinanceWebSocketClient` — raw WS client |
| `src/pocketquant/core/domain/market_data/interfaces.py:16` | `IRealtimeQuoteProvider` Protocol (`@runtime_checkable`, 9 members) |
| `src/pocketquant/app/market_data/app_services/quote_app_service.py` | `QuoteAppService` — consumes ticks, writes to Redis + bar builder |
| `src/pocketquant/app/market_data/app_services/ws_subscription_manager.py` | `WsSubscriptionManager` — 5s reconcile loop vs `tracked_symbols` |
| `src/pocketquant/app/di/market_data.py:26` | DI wiring (scope=APP singleton) |
| `src/pocketquant/app/main_extensions.py:110` | `start_quote_feed` lifespan hook |

### URLs

- Single: `wss://stream.binance.com:9443/ws/{symbol}@aggTrade`
- Combined: `wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade`

### Flow

1. FastAPI lifespan calls `start_quote_feed` → spawns 2 background asyncio tasks:
   - `provider.run_forever()` — receive loop + reconnect
   - `WsSubscriptionManager.run()` — reconcile loop
2. `WsSubscriptionManager` every 5s diffs `tracked_symbols` MongoDB collection vs current WS subscriptions:
   - `to_add = desired - current`
   - `to_remove = current - desired`
   - Calls `subscribe()` / `unsubscribe()` with 20ms throttle (50/s cap to avoid IP ban).
3. Binance `@aggTrade` frames → `_handle_frame` → `aggtrade_to_quote_dict` → `QuoteAppService.on_quote_update` callback.
4. Callback:
   - Writes latest quote to Redis cache (`CACHE_KEY_QUOTE_LATEST`, TTL `TTL_QUOTE_LATEST`).
   - Clamps negative volume deltas to 0.0 (spec-violation guard).
   - Forwards `QuoteTick` to `BarAppService.add_tick` (bar aggregation).
5. **Reconnect:** exponential backoff `1s → 60s` inside `run_forever`. Auto re-subscribes by rebuilding URL from current `_subscriptions` dict.

### Key design points

- `IRealtimeQuoteProvider` is a `@runtime_checkable` **Protocol** (not ABC) — future providers (Kraken, Coinbase) satisfy via structural subtyping.
- WS client is a **singleton** in `Scope.APP` — shared between `QuoteAppService`, `WsSubscriptionManager`, and any status handler.
- Subscription state lives in the client (`_subscriptions: dict[symbol_key, (symbol, exchange, callback)]`); reconcile manager is the sole writer by convention.

---

## B. Trading Order/Position Stream (OKX)

### Files

| Path | Role |
|---|---|
| `src/pocketquant/core/infra/brokers/okx/websocket/okx_websocket_client.py:26` | `OkxWebSocketClient` — auth + subscribe + iterate |
| `src/pocketquant/core/infra/brokers/okx/websocket/okx_reconnection_handler.py:22` | `OkxReconnectionHandler` — backoff + REST state sync |
| `src/pocketquant/core/infra/brokers/okx/websocket/okx_auth.py` | HMAC-SHA256 login message builder |
| `src/pocketquant/core/infra/brokers/okx/websocket/okx_message_parser.py` | Frame routing (orders / positions) |
| `src/pocketquant/core/infra/brokers/okx/websocket/okx_order_mapper.py` | OKX → `OrderResult` mapping, terminal-state detection |
| `src/pocketquant/core/infra/brokers/okx/websocket/okx_position_mapper.py` | OKX → position update mapping |
| `src/pocketquant/core/infra/brokers/okx/okx_broker.py:295` | `_ws_listener` — orchestrates full lifecycle |

### Flow

1. `OKXBroker.subscribe_order_updates(callback)` registers callback; first call spawns `_ws_listener` task.
2. Listener:
   - `connect()` — opens WS, sends HMAC-SHA256 login, waits for `event=login, code=0`.
   - Starts custom heartbeat task (`PING_INTERVAL=25s`, OKX times out at 30s).
   - `subscribe([{channel:"orders",instType:"SWAP"}, {channel:"positions",instType:"SWAP"}])`.
   - `async for message in client` — iterator filters out pong + event messages, yields only data frames.
3. Messages routed by `OkxMessageParser.parse`:
   - **orders** → `OkxOrderMapper.to_order_result` → dedupe terminal states via `_seen_terminal_orders: set[str]` → `_notify_callbacks` fires registered callbacks (e.g. `ResultCollector.on_fill` for backtests).
   - **positions** → `OkxPositionMapper.to_position_update` → **logged only** (no EventBus emission today; see Known Issues).
4. **Reconnect (`OkxReconnectionHandler`):**
   - Exponential backoff: `1s → 30s` (cap), multiplier `2.0`.
   - Circuit breaker: pause **5 minutes** after **10 consecutive failures**, then reset and retry.
   - On successful reconnect: re-subscribe channels, then `_sync_state` calls REST `get_orders_history(instType=SWAP, limit=100)` to refresh dedupe set — prevents re-processing orders that filled while disconnected.
5. **Disconnect detection:** `on_disconnect` callback wired from `OkxWebSocketClient` to `OKXBroker._on_ws_disconnect` → triggers reconnection handler.

### Consumers

- `OrderAppService` (live trading) — receives order results via `subscribe_order_updates`.
- `ResultCollector.on_fill` (`src/pocketquant/backtest/engine/result_collector.py`) — for backtest engine.

---

## DI Wiring

```python
# src/pocketquant/app/di/market_data.py
@provide(scope=Scope.APP)
def get_realtime_quote_provider(self) -> IRealtimeQuoteProvider:
    """Singleton WS client shared by QuoteAppService, WsSubscriptionManager."""
    return BinanceWebSocketClient()
```

OKX WS client is **not** in the DI container — it's created lazily inside `OKXBroker._ws_listener` when `subscribe_order_updates` is first called. `OKXBroker` itself comes from `BrokerFactory` (`src/pocketquant/app/di/broker_factory.py`).

---

## Lifespan / Startup

```python
# src/pocketquant/app/main_extensions.py:110
async def start_quote_feed(container, app):
    quote_svc = await container.get(QuoteAppService)
    sub_mgr = await container.get(WsSubscriptionManager)
    await quote_svc.start()                         # spawns provider.run_forever()
    app.state.ws_task = quote_svc.ws_task
    app.state.subscription_task = asyncio.create_task(sub_mgr.run())
```

`stop_quote_feed` cancels both tasks with 5s timeout each, then `provider.disconnect()`.

---

## C. SSE Server→Frontend Streams

### Bars SSE

**Route:** GET `/api/v1/market-data/bars/stream/{symbol}?interval={interval}`

**Files:**
- `src/pocketquant/app/routes/market_data_ohlcv.py` — SSE route endpoint

**Flow:**
1. Client opens EventSource connection → server enters poll loop.
2. Every 1.0s: read `bar:current:{symbol}:{interval}` from Redis.
3. Compare against last emitted bar (track `bar_start`, `volume`, etc.):
   - Emit only if bar_start changed or volume/price increased
4. Merge Redis in-progress bar + MongoDB closed-bar fallback (for recovery after disconnect).
5. Return SSE event:
   ```
   data: {"symbol": "BTCUSDT:BINANCE", "interval": "1m", "bar_start": 1..., "open": 101.0, ...}
   ```
6. Payload fields: `symbol`, `interval`, `bar_start`, `open`, `high`, `low`, `close`, `volume`, `tick_count`, `is_in_progress`, `staleness_ms`.
7. **Disconnect detection:** `asyncio.CancelledError` caught silently; client EventSource auto-retries.
8. **Max lag:** ~1.2s (1s poll cycle + overhead).

**Redis Key Lifecycle:**
- Key: `bar:current:{symbol}:{interval}`
- TTL: `max(300, interval_seconds*2)` (prevents stale accumulation)
- Deleted on bar completion by `BarAppService._cache_current_bar`
- Last update timestamp injected for staleness calculation

---

### Quotes SSE

**Route:** GET `/api/v1/quotes/stream/{symbol}`

**Files:**
- `src/pocketquant/app/routes/market_data_quotes.py` — SSE route endpoint

**Flow:**
1. Client opens EventSource connection → server enters poll loop.
2. Every 0.5s: read `quote:latest:{symbol}` from Redis.
3. Compare against last emitted quote (track `last_price`, `volume`):
   - Emit only if `last_price` or `volume` changed
4. Fallback: If Redis miss, REST GET `/api/v1/market-data/quotes/latest/{symbol}` (for initial cache load).
5. Return SSE event:
   ```
   data: {"symbol": "BTCUSDT:BINANCE", "last_price": 101.50, "bid": 101.48, "ask": 101.52, "volume": 1000, "change": 0.5, "change_percent": 0.49, "ts": 1...}
   ```
6. **Max lag:** <700ms (0.5s poll cycle + overhead).

**Redis Key Lifecycle:**
- Key: `quote:latest:{symbol}`
- TTL: ~60s (updated by `QuoteAppService.on_quote_update` on each tick)
- Populated by Binance `@aggTrade` → `BinanceWebSocketClient._handle_frame` → `QuoteAppService.on_quote_update`

---

### Frontend Consumers

**React Hooks:**

1. **`use-realtime-bar.ts`** — Binds to bars SSE
   - File: `web/src/hooks/use-realtime-bar.ts`
   - Opens EventSource to `/api/v1/market-data/bars/stream/{symbol}?interval={interval}`
   - 30s stale threshold: marks data stale if no event received (visual indicator)
   - Schedules OHLCV refetch ~5s after bar rollover to sync closed bar with REST
   - Monotonic time guard: drops out-of-order events (guards against clock skew)

2. **`use-realtime-quote.ts`** — Binds to quotes SSE
   - File: `web/src/hooks/use-realtime-quote.ts`
   - Opens EventSource to `/api/v1/quotes/stream/{symbol}`
   - 10s stale threshold: falls back to REST polling if SSE inactive
   - Fallback: GET `/api/v1/quotes/latest/{symbol}` before SSE connects (warm start)

---

## Known Issues

### 1. OKX heartbeat races with message iterator
`OkxWebSocketClient._heartbeat_loop` does `await self._ws.recv()` to wait for `"pong"`, which **competes with** `__aiter__`'s `recv()`. There is only one underlying socket. Today, a non-pong frame arriving during the heartbeat window is logged and **dropped** (`okx_websocket_client.py:208-212`).
**Impact:** silent data loss for order/position events under load.
**Fix direction:** single recv-task → typed `asyncio.Queue` demux (pings vs data).

### 2. OKX position channel data is discarded
`_handle_position_update` (`okx_broker.py:396-411`) only logs. Existing TODO comment says "Could emit `PositionUpdatedEvent` via EventBus".
**Impact:** No live position cache update; only available via REST polling.

### 3. Binance unsubscribe defers reconnect
`BinanceWebSocketClient.unsubscribe` removes the entry from `_subscriptions` but does **not** reconnect with the new URL. The combined stream URL stays wrong until the next connection drop.
**Impact:** Unsubscribed symbol's frames keep arriving until natural reconnect.

### 4. Two WS clients, zero shared abstraction
Binance and OKX clients reimplement: connect, backoff, heartbeat, reconnect, message iteration — with different control flow (Binance reconnects inside `run_forever`; OKX uses separate `OkxReconnectionHandler`) and different telemetry naming.

### 5. SSE poll latency vs WebSocket bidirectional trade-off
SSE polling adds ~0.5–1.2s latency (poll cycle overhead) compared to WebSocket's event-driven push. For bar aggregation this is acceptable (intervals typically ≥1m). For quote UX under fast market conditions, consider WebSocket upgrade in future if 700ms+ RTT becomes a problem.
- Current: SSE polls every 0.5s (quotes) / 1s (bars), emits only on change (minimal bandwidth)
- Alternative: FastAPI `@app.websocket` + per-symbol rooms. Bidirectional, event-driven, but higher complexity + connection tracking overhead

---

## Tests

- `tests/unit/market_data/binance/test_binance_websocket_client.py` — Binance WS unit tests (~15 cases).
- `tests/unit/di/test_di_data_provider.py` — DI resolution and `IRealtimeQuoteProvider` Protocol conformance.

---

## Unresolved Questions

- Is a frontend live-tick stream a near-term requirement, or is REST polling acceptable?
- Are the OKX heartbeat race / dropped events a tolerated edge case, or has it caused production incidents?
