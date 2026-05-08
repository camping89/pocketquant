---
status: completed
---

# Phase 01 — Binance providers (REST + WS @aggTrade)

## Context links

- Brainstorm: [`brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md`](../reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md)
- Research: [`researcher-03-okx-vs-binance.md`](./research/researcher-03-okx-vs-binance.md)
- Existing impl reused: `pocketquant/scripts/backfill_1m_from_binance.py` (REST kline mapper)
- Pattern reference: `pocketquant-core/src/pocketquant/core/infrastructure/tradingview/tradingview_websocket_client.py` (run_forever, reconnection skeleton — TV folder deleted in Phase 03 after this phase)

## Overview

- **Priority:** P1 — blocks Phase 03 + 04
- **Status:** pending
- **Effort:** 5h
- **Description:** Build `BinanceClient` (REST `IDataProvider` impl) + `BinanceWebSocketClient` (realtime `@aggTrade` per-trade stream). Reuse mapping logic from `backfill_1m_from_binance.py`.

## Key insights

- Binance REST `/api/v3/klines`: 1000-bar limit, 2 weight/call, 1200 weight/min budget → ≤600 calls/min sustainable
- WS `@aggTrade` stream: per-trade event with `p` (price), `q` (quantity = DELTA volume), `T` (trade time UTC ms), `s` (symbol). No cumulative parsing required.
- `@aggTrade` event rate: 1000+ events/sec on BTCUSDT during volatility — must profile downstream lock contention
- Symbol passthrough: PocketQuant `BTCUSDT` → Binance native (zero mapping)
- Backfill script already proves kline parsing correctness (production validated 5080 bars)

## Requirements

### Functional
- `BinanceClient` implements `IDataProvider`: `fetch_ohlcv(symbol, exchange, interval, n_bars)` returns `list[Bar]` ascending
- Supports all enum intervals: `1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 1M`
- Pagination: chunks of 1000 bars via `startTime`/`endTime` cursor; merges chunks
- `BinanceWebSocketClient`: `connect`, `disconnect`, `subscribe(symbol, exchange, callback)`, `unsubscribe`, `run_forever`, `is_connected`, `subscription_count`, `subscriptions`, `last_tick_at`
- Stream URL per subscription: `wss://stream.binance.com:9443/ws/{symbol_lower}@aggTrade`
- Multi-subscription: combined stream `wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade`
- Callback emits dict matching downstream `QuoteAppService.on_quote_update` contract: keys `symbol_key, timestamp, last_price, volume, bid, ask, change, change_percent, open_price, high_price, low_price, prev_close`
- `volume` field in callback dict = **delta** (event `q`), NOT cumulative
- Fields not provided by `@aggTrade` (`bid`, `ask`, `open_price`, `high_price`, `low_price`, `prev_close`, `change`) emit as `None` or `0.0` — downstream tolerant

### Non-functional
- Rate limiting: REST 100ms inter-call sleep; abort on HTTP 429 with backoff (2/3/5 min progressive per Binance policy)
- Reconnection: exponential backoff 1s → 60s max
- Logging: structlog `binance.fetch_started`, `binance.fetch_completed`, `binance_ws.connected`, `binance_ws.aggtrade_received`
- Each file ≤200 LOC. Split mapper helpers into `binance_mappers.py` if needed.

## Architecture

```
QuoteAppService.on_quote_update(dict)        ◄── unchanged callback signature
        ▲
        │ dict with volume = DELTA (per-trade q)
        │
BinanceWebSocketClient ──► subscribe(BTCUSDT, BINANCE, cb)
        │
        └── ws://stream.binance.com:9443/ws/btcusdt@aggTrade
                │
                └── parse aggTrade JSON → callback dict
                        timestamp = T (ms→datetime UTC)
                        last_price = float(p)
                        volume = float(q)  (delta, not cumulative)


SyncSymbolHandler (cron)
        │
        ▼
BinanceClient.fetch_ohlcv("BTCUSDT", "BINANCE", Interval.MINUTE_1, 100)
        │
        ▼
GET /api/v3/klines?symbol=BTCUSDT&interval=1m&limit=100
        │
        ▼
list[Bar]
```

## Related code files

**Create:**
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/__init__.py`
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_client.py` (REST, ≤200 LOC)
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_mappers.py` (kline → Bar, aggTrade frame → quote dict)
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_websocket_client.py` (≤200 LOC)
- `packages/pocketquant-core/tests/unit/infrastructure/binance/test_binance_client.py`
- `packages/pocketquant-core/tests/unit/infrastructure/binance/test_binance_websocket_client.py`

**Read for reference:**
- `pocketquant/scripts/backfill_1m_from_binance.py` (extract `kline_to_bar`, `INTERVAL_TO_BINANCE`)
- `pocketquant-core/src/pocketquant/core/infrastructure/tradingview/tradingview_websocket_client.py` (run_forever skeleton — copied before deletion in Phase 03)
- `pocketquant-core/src/pocketquant/core/infrastructure/tradingview/base.py` (IDataProvider contract)

## Implementation steps

1. Create folder `infrastructure/binance/` + `__init__.py` exporting `BinanceClient`, `BinanceWebSocketClient`.
2. Move `INTERVAL_TO_BINANCE` map + `kline_to_bar` from script → `binance_mappers.py`. Extend map: `1w, 1M, 6h, 8h, 12h, 3d`. Add `aggtrade_to_quote_dict(event: dict, symbol: str, exchange: str) -> dict`.
3. Build `binance_client.py`:
   - `__init__(self, settings: Settings, base_url: str = "https://api.binance.com")`
   - `async def fetch_ohlcv(symbol, exchange, interval, n_bars=1000)` — single chunk if `n_bars≤1000`; cursor-paginate otherwise.
   - `async def search_symbols(query, exchange=None)` — stub returning `[]` (KISS).
   - `def close(self)` — close httpx client.
   - Implements `IDataProvider`.
4. Build `binance_websocket_client.py`:
   - Mirror TV WS shape: `connect`, `disconnect`, `subscribe`, `unsubscribe`, `run_forever`, `is_connected`, `subscription_count`, `subscriptions`, `last_tick_at`.
   - Stream URL: `wss://stream.binance.com:9443/ws/{symbol_lower}@aggTrade` (single sub) or combined-stream endpoint (multi).
   - On message: `event = json.loads(frame)`; if event has `e == "aggTrade"`, call `aggtrade_to_quote_dict(event, symbol, exchange)` → invoke callback.
   - Reconnection: exponential backoff 1s → 60s; re-subscribe on reconnect.
5. Unit tests:
   - `test_binance_client.py`: parametrize 5 intervals, mock httpx, assert kline → Bar mapping; pagination cursor advances; HTTP 429 raises with logged backoff.
   - `test_binance_websocket_client.py`: feed canned `@aggTrade` frames (`{"e":"aggTrade","E":...,"s":"BTCUSDT","p":"50000.00","q":"0.01","T":...}`), assert callback receives `volume == 0.01` (delta), `last_price == 50000.0`, `timestamp` matches `T`. Reconnection backoff doubles per failure to 60s cap. Subscription_count tracking.
6. Run `just test-pkg core` — all pass.
7. Run `just lint && just types` — clean.

## Todo list

- [x] Create `infrastructure/binance/` folder + `__init__.py`
- [x] `binance_mappers.py` with extended interval map + `kline_to_bar` + `aggtrade_to_quote_dict`
- [x] `binance_client.py` implementing `IDataProvider`
- [x] `binance_websocket_client.py` consuming `@aggTrade`
- [x] Unit tests for REST client (≥6 cases)
- [x] Unit tests for WS client (≥5 cases including aggTrade frame parsing + reconnection)
- [x] Lint + type-check clean
- [x] All core unit tests green

## Success criteria

- `BinanceClient.fetch_ohlcv("BTCUSDT", "BINANCE", Interval.MINUTE_1, 1000)` returns 1000 `Bar` entities with `H>L` and `volume>0` for each.
- `BinanceWebSocketClient` connects, subscribes BTCUSDT, callback fires within 5s with `last_price > 0` and `volume > 0` (per-trade delta).
- Test: feeding two `@aggTrade` frames `q=0.5` then `q=0.3` results in two callback invocations with `volume=0.5` and `volume=0.3` respectively (NOT 0.5 then 0.8).
- Test coverage ≥85% on new files.
- No file exceeds 200 LOC (split if needed).

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Binance returns 429 (IP rate limit) during pagination | Low | High | Inter-call 100ms sleep; exponential backoff on 429; weight header monitor |
| WS combined-stream subscription limit exceeded (1024 streams) | Very low | Medium | Cap subscriptions at 50 (current tracked_symbols size); document limit |
| `@aggTrade` high event rate (1000+/sec on BTCUSDT) overloads `BarAppService` | Medium | High | Profile lock contention under load; per-symbol lock fallback if global `_bars` dict bottlenecks |
| WS message format change (Binance versioning) | Low | High | Pin to `/ws/` v1 endpoint; integration test against live endpoint quarterly |
| `q` field interpretation drift (delta vs cumulative misread) | Low | Critical | Unit test asserts callback emits raw `q` per-event (not summed); doc-string contract |
| `httpx.AsyncClient` connection leak | Low | Low | Async context manager; `close()` in `IDataProvider` |

## Security considerations

- No auth required for public Binance endpoints (REST + WS public streams).
- No secrets to leak.
- Validate `symbol` input format (uppercase A-Z0-9, length 6-12) before injecting into URL — defense against URL injection.

## Next steps

- Phase 03 wires `BinanceClient` + `BinanceWebSocketClient` into DI providers and deletes `infrastructure/tradingview/`.
- Phase 04 uses `BinanceClient` for 2y re-sync.

## Outcome

Delivered 4 new files in `infrastructure/binance/`: `__init__.py`, `binance_client.py` (IDataProvider REST impl, ≤200 LOC), `binance_websocket_client.py` (@aggTrade WS client), `binance_mappers.py` (kline→Bar, aggTrade→quote mapping). 30 unit tests added (6 REST, 5 WS, coverage ≥85%, no regressions). Lint + type-check clean. See [fullstack-260507-1820-phase-01-binance-providers-complete.md](../reports/fullstack-260507-1820-phase-01-binance-providers-complete.md).

## Unresolved questions

1. `@aggTrade` does not provide bid/ask/24h-change — should `BinanceWebSocketClient` issue a separate `@ticker` stream subscription per symbol to fill those fields? **Recommendation:** Defer (YAGNI). Current handlers tolerate `None`. Revisit when bid/ask required for order placement.
2. Should the callback throttle/batch high-rate events (e.g. coalesce per 100ms window)? **Recommendation:** Phase 1 emits raw; revisit if Phase 2/4 profiling shows lock contention.
