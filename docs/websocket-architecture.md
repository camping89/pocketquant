# WebSocket Architecture

**Status:** Current as of 2026-05-26
**Scope:** Outbound WebSocket clients only — no server-side (FastAPI) WebSocket endpoint exists.

---

## Overview

Two completely separate outbound WebSocket subsystems run inside the FastAPI process:

1. **Market-Data Stream (Binance public `@aggTrade`)** — singleton, app-wide, ingests realtime ticks.
2. **Trading Order/Position Stream (OKX private channels)** — per-broker instance, ingests order/position updates.

Frontend (`pocketquant-web` SPA) talks to backend over **REST only**. There is no server→client live stream today.

```
┌──────────────────────────────────────────────────────────────┐
│                  PocketQuant FastAPI app                     │
│                                                              │
│  ┌────────────────────────┐    ┌─────────────────────────┐  │
│  │ Market Data WS         │    │ OKX Trading WS          │  │
│  │ (singleton, app-wide)  │    │ (per-broker instance)   │  │
│  └────────────────────────┘    └─────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
            │                                  │
            ▼                                  ▼
   Binance public stream             OKX private channels
   wss://stream.binance.com          wss://ws.okx.com (priv)
   @aggTrade                         orders + positions
```

---

## A. Market-Data Stream (Binance)

### Files

| Path | Role |
|---|---|
| `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_websocket_client.py:33` | `BinanceWebSocketClient` — raw WS client |
| `packages/pocketquant-core/src/pocketquant/core/infrastructure/realtime_quote_provider.py:16` | `IRealtimeQuoteProvider` Protocol (`@runtime_checkable`, 9 members) |
| `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py:18` | `QuoteAppService` — consumes ticks, writes to Redis + bar builder |
| `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/ws_subscription_manager.py:22` | `WsSubscriptionManager` — 5s reconcile loop vs `tracked_symbols` |
| `packages/pocketquant-api/src/pocketquant/api/di/market_data.py:26` | DI wiring (scope=APP singleton) |
| `packages/pocketquant-api/src/pocketquant/api/main_extensions.py:110` | `start_quote_feed` lifespan hook |

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
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/websocket/okx_websocket_client.py:26` | `OkxWebSocketClient` — auth + subscribe + iterate |
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/websocket/okx_reconnection_handler.py:22` | `OkxReconnectionHandler` — backoff + REST state sync |
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/websocket/okx_auth.py` | HMAC-SHA256 login message builder |
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/websocket/okx_message_parser.py` | Frame routing (orders / positions) |
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/websocket/okx_order_mapper.py` | OKX → `OrderResult` mapping, terminal-state detection |
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/websocket/okx_position_mapper.py` | OKX → position update mapping |
| `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_broker.py:295` | `_ws_listener` — orchestrates full lifecycle |

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
- `ResultCollector.on_fill` (`pocketquant-backtest/src/.../engine/result_collector.py:30`) — for backtest engine.

---

## DI Wiring

```python
# packages/pocketquant-api/src/pocketquant/api/di/market_data.py
@provide(scope=Scope.APP)
def get_realtime_quote_provider(self) -> IRealtimeQuoteProvider:
    """Singleton WS client shared by QuoteAppService, WsSubscriptionManager."""
    return BinanceWebSocketClient()
```

OKX WS client is **not** in the DI container — it's created lazily inside `OKXBroker._ws_listener` when `subscribe_order_updates` is first called. `OKXBroker` itself comes from `BrokerFactory` (`packages/pocketquant-api/src/pocketquant/api/di/broker_factory.py`).

---

## Lifespan / Startup

```python
# packages/pocketquant-api/src/pocketquant/api/main_extensions.py:110
async def start_quote_feed(container, app):
    quote_svc = await container.get(QuoteAppService)
    sub_mgr = await container.get(WsSubscriptionManager)
    await quote_svc.start()                         # spawns provider.run_forever()
    app.state.ws_task = quote_svc.ws_task
    app.state.subscription_task = asyncio.create_task(sub_mgr.run())
```

`stop_quote_feed` cancels both tasks with 5s timeout each, then `provider.disconnect()`.

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

### 5. No server-side WS endpoint
Frontend cannot receive live ticks. If realtime UI is desired, options are:
- **SSE** endpoint subscribing to a Redis pub/sub channel published from `QuoteAppService.on_quote_update`. Lighter for one-way streams.
- **FastAPI `@app.websocket`** + connection tracking. More flexible (bidirectional) but more code.

---

## Tests

- `packages/pocketquant-core/tests/unit/infrastructure/binance/test_binance_websocket_client.py` — Binance WS unit tests (~15 cases).
- `packages/pocketquant-api/tests/unit/di/test_di_data_provider.py` — DI resolution and `IRealtimeQuoteProvider` Protocol conformance.

---

## Unresolved Questions

- Is a frontend live-tick stream a near-term requirement, or is REST polling acceptable?
- Are the OKX heartbeat race / dropped events a tolerated edge case, or has it caused production incidents?
- `tests/manual/run_stream_quotes.py:18` still imports `tradingview_websocket_client` which appears removed — stale manual script or in-progress migration?
