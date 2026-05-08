# Phase 01 — Binance Providers Implementation Report

**Date:** 2026-05-08
**Plan:** `plans/260507-1835-vps-bars-mismatch-tv-pro-fix/phase-01-binance-providers.md`

## Files Created

| File | LOC | Notes |
|---|---|---|
| `infrastructure/binance/__init__.py` | 5 | Exports BinanceClient, BinanceWebSocketClient |
| `infrastructure/binance/binance_client.py` | 131 | REST IDataProvider impl, httpx, pagination |
| `infrastructure/binance/binance_websocket_client.py` | 170 | @aggTrade WS, reconnect, combined-stream |
| `tests/unit/infrastructure/binance/__init__.py` | 0 | Empty |
| `tests/unit/infrastructure/binance/test_binance_client.py` | 215 | 13 test cases |
| `tests/unit/infrastructure/binance/test_binance_websocket_client.py` | 315 | 17 test cases |

**Modified (mapper fix):**
- `infrastructure/binance/binance_mappers.py` — removed `HOUR_6/8/12, DAY_3` refs (not in Interval enum)

## Tests

- **Total:** 97 passed (30 new + 67 pre-existing), 0 failed
- REST client: 13 cases — 4x interval parametrize, field mapping, H>=L invariant, single-call, multi-chunk, cursor regression, HTTP 429, invalid symbol, empty response, close(), search_symbols stub
- WS client: 17 cases — volume delta, last_price, timestamp, two-frame delta (not cumulative), combined-stream envelope, non-aggTrade ignored, async callback, last_tick_at, subscribe/unsubscribe counts, backoff doubling, backoff cap, reconnect resets delay, run_forever reconnects

## Verification

```
just test-pkg core   → 97 passed, 0 failed
ruff check (new files) → 0 errors (2 import-sort auto-fixed)
pyright (binance/ dir) → 0 errors, 0 warnings
```

## Issues Encountered

1. **Mapper had nonexistent enum values** (`HOUR_6`, `HOUR_8`, `HOUR_12`, `DAY_3`) — stripped from `INTERVAL_TO_BINANCE`; documented with NOTE comment. Enum extension deferred to a future phase.
2. **`respx` not installed** — rewrote REST tests using `unittest.mock` patching `httpx.AsyncClient.get` directly; no new dep added.
3. **websockets v16 `connect()` returns `__await__` object, not coroutine** — `patch(..., side_effect=async_def)` used in tests instead of `return_value=AsyncMock`.

## Concerns

None blocking. The `ConnectionClosed.code/.reason` deprecation warnings (websockets 13.1+) come from test setup using `ConnectionClosed(None, None)` — only in tests, not production path.
