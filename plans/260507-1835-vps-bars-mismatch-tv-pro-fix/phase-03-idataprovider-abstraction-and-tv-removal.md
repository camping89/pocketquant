---
status: completed
---

# Phase 03 — IDataProvider abstraction + full TradingView removal

## Context links

- Brainstorm Phase 3: [`brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md`](../reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md) §"Phase 3"
- Existing interface: `pocketquant-core/src/pocketquant/core/infrastructure/tradingview/base.py` (relocates to `infrastructure/data_provider.py`)
- DI files: `pocketquant-api/src/pocketquant/api/di/infrastructure.py`, `market_data.py`
- Phase 01 deliverables: `BinanceClient`, `BinanceWebSocketClient`

## Overview

- **Priority:** P1 — required to switch production to Binance
- **Status:** pending
- **Effort:** 2h
- **Description:** Wire `BinanceClient` + `BinanceWebSocketClient` into Dishka DI providers as the single implementations. **Delete** `infrastructure/tradingview/` folder + tests + env vars + `tvDatafeed` dependency entirely. No env flag, no fallback.

## Key insights

- Single-provider design: no `MARKET_DATA_PROVIDER` env flag, no swap logic — KISS
- `IDataProvider` relocates from `infrastructure/tradingview/base.py` → `infrastructure/data_provider.py` (neutral path); no legacy re-export shim (TV folder deleted in same phase)
- `IRealtimeQuoteProvider` Protocol still useful for: type hints in `QuoteAppService` / `WsSubscriptionManager`, future provider extensibility (e.g., OKX), runtime structural validation
- Cron `sync_jobs.py` calls `IDataProvider`; no signature change needed
- Removal scope: `tvDatafeed` from `pyproject.toml`, `TRADINGVIEW_USERNAME/PASSWORD` from `.env.example` + `Settings`, all `tradingview/` folder files + tests

## Requirements

### Functional
- Move `IDataProvider` ABC to `infrastructure/data_provider.py`
- Create `IRealtimeQuoteProvider` Protocol at `infrastructure/realtime_quote_provider.py` with 9 WS members
- Dishka DI providers return `BinanceClient` / `BinanceWebSocketClient` directly — no conditional
- Delete `infrastructure/tradingview/` folder and its tests
- Delete `tradingview_username`, `tradingview_password` from `Settings`
- Remove `TRADINGVIEW_USERNAME`, `TRADINGVIEW_PASSWORD` from `.env.example`
- Remove `tvdatafeed` from `pyproject.toml` (verify no other consumer via grep)
- All handlers depend on `IDataProvider` / `IRealtimeQuoteProvider` (abstract types)

### Non-functional
- `grep -r "tvDatafeed\|tradingview" packages/ --include="*.py"` returns zero hits post-phase
- `grep -r "TRADINGVIEW_USERNAME\|TRADINGVIEW_PASSWORD" pocketquant/` returns zero hits post-phase
- Settings parsing: no TV-related fields
- Document extension point in `system-architecture.md` (Phase 05)

## Architecture

```
Settings (no provider flag)
        │
        ▼
InfrastructureProvider.get_data_provider(settings) -> IDataProvider
        │
        └── BinanceClient(settings)
                    │
                    ▼
                SyncSymbolHandler, integrity_jobs, ...

MarketDataProvider.get_realtime_quote_provider(settings) -> IRealtimeQuoteProvider
        │
        └── BinanceWebSocketClient()
                    │
                    ▼
                QuoteAppService.provider (typed as IRealtimeQuoteProvider)


DELETED:
    packages/pocketquant-core/src/pocketquant/core/infrastructure/tradingview/  (entire folder)
    packages/pocketquant-core/tests/unit/infrastructure/tradingview/            (entire folder)
    packages/pocketquant-core/tests/integration/infrastructure/tradingview/     (entire folder)
    Settings.tradingview_username, Settings.tradingview_password
    .env.example: TRADINGVIEW_USERNAME, TRADINGVIEW_PASSWORD
    pyproject.toml: tvdatafeed dep
```

## Related code files

**Create:**
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/data_provider.py` — `IDataProvider` ABC (relocated from `tradingview/base.py`)
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/realtime_quote_provider.py` — `IRealtimeQuoteProvider` Protocol (9 WS members, `@runtime_checkable`)

**Modify:**
- `packages/pocketquant-core/src/pocketquant/core/config.py` — remove `tradingview_username`, `tradingview_password` from `Settings`
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_client.py` — import `IDataProvider` from new path
- `packages/pocketquant-api/src/pocketquant/api/di/infrastructure.py` — `get_data_provider(settings) -> IDataProvider` returns `BinanceClient`
- `packages/pocketquant-api/src/pocketquant/api/di/market_data.py` — `get_realtime_quote_provider(settings) -> IRealtimeQuoteProvider` returns `BinanceWebSocketClient`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py` — annotation `provider: IRealtimeQuoteProvider`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/ws_subscription_manager.py` — annotation `IRealtimeQuoteProvider`
- All handlers/sites importing `TradingViewClient` directly — swap to `IDataProvider`
- `pocketquant/.env.example` (or `.env.sample`) — drop `TRADINGVIEW_*` lines
- `packages/pocketquant-core/pyproject.toml` (and any other) — drop `tvdatafeed` dep

**Delete:**
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/tradingview/` (entire folder)
- `packages/pocketquant-core/tests/unit/infrastructure/tradingview/` (entire folder)
- `packages/pocketquant-core/tests/integration/infrastructure/tradingview/` (entire folder, if exists)

**Read for reference:**
- `pocketquant-api/src/pocketquant/api/di/infrastructure.py:32-34` (current `get_tv_client`)
- `pocketquant-api/src/pocketquant/api/di/market_data.py:22-25` (current `get_ws_client`)

## Implementation steps

1. Create `infrastructure/data_provider.py` with `IDataProvider` ABC (copy contents from `tradingview/base.py`).
2. Create `infrastructure/realtime_quote_provider.py` with `IRealtimeQuoteProvider` Protocol (`@runtime_checkable`, 9 members).
3. Update `BinanceClient` import: `from pocketquant.core.infrastructure.data_provider import IDataProvider`.
4. Update `Settings` in `config.py`: delete `tradingview_username`, `tradingview_password` fields.
5. Update `InfrastructureProvider`:
   ```python
   @provide(scope=Scope.APP)
   def get_data_provider(self, settings: Settings) -> IDataProvider:
       return BinanceClient(settings=settings)
   ```
   Remove `get_tv_client`. Update direct `TradingViewClient` injection sites to depend on `IDataProvider`.
6. Update `MarketDataProvider`:
   ```python
   @provide(scope=Scope.APP)
   def get_realtime_quote_provider(self, settings: Settings) -> IRealtimeQuoteProvider:
       return BinanceWebSocketClient()
   ```
7. Update `QuoteAppService.__init__(provider: IRealtimeQuoteProvider)` and `WsSubscriptionManager` annotations.
8. Grep `TradingViewClient`, `TradingViewWebSocketClient`, `tvDatafeed`, `tv_datafeed` across `packages/`. Replace with abstract types or remove. Final grep returns 0 hits.
9. Delete folders:
   - `packages/pocketquant-core/src/pocketquant/core/infrastructure/tradingview/`
   - `packages/pocketquant-core/tests/unit/infrastructure/tradingview/`
   - `packages/pocketquant-core/tests/integration/infrastructure/tradingview/` (if exists)
10. Update `pyproject.toml`: remove `tvdatafeed` from `[project.dependencies]` (or `[tool.uv.sources]`). Verify via grep no other package imports `tvDatafeed`.
11. Update `.env.example`: delete `TRADINGVIEW_USERNAME`, `TRADINGVIEW_PASSWORD` lines.
12. Add unit test `test_di_data_provider.py`:
    - Container resolves `IDataProvider` → `BinanceClient` instance
    - Container resolves `IRealtimeQuoteProvider` → `BinanceWebSocketClient` instance
    - Both pass `isinstance(client, IRealtimeQuoteProvider)` (runtime_checkable)
13. Run `just test && just lint && just types`.

## Todo list

- [x] Create `infrastructure/data_provider.py` with `IDataProvider`
- [x] Create `infrastructure/realtime_quote_provider.py` with `IRealtimeQuoteProvider` Protocol
- [x] Update `BinanceClient` import path
- [x] Remove TV fields from `Settings`
- [x] Replace `get_tv_client` with `get_data_provider` in DI (BinanceClient only)
- [x] Replace `get_ws_client` with `get_realtime_quote_provider` (BinanceWebSocketClient only)
- [x] Update `QuoteAppService` + `WsSubscriptionManager` annotations
- [x] Update injection sites to depend on abstractions
- [x] Delete `infrastructure/tradingview/` folder
- [x] Delete TV unit + integration test folders
- [x] Remove `tvdatafeed` from `pyproject.toml`
- [x] Update `.env.example` (drop TV creds)
- [x] Add DI unit test
- [x] Final grep guard: 0 `tvDatafeed`/`tradingview` hits
- [x] All tests + lint + types green

## Success criteria

- `infrastructure/tradingview/` folder does not exist (verifiable: `ls packages/pocketquant-core/src/pocketquant/core/infrastructure/tradingview` errors)
- `grep -r "tvDatafeed" packages/ --include="*.py"` returns 0 hits
- `grep -r "tradingview" packages/ --include="*.py"` returns 0 hits (or only docs/comments — none in active code)
- `grep -r "TRADINGVIEW_USERNAME\|TRADINGVIEW_PASSWORD" pocketquant/` returns 0 hits
- `tvdatafeed` absent from all `pyproject.toml` files
- DI test green: container resolves `BinanceClient` for `IDataProvider`, `BinanceWebSocketClient` for `IRealtimeQuoteProvider`
- App boots cleanly without any `TRADINGVIEW_*` env var set
- No file >200 LOC

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hidden import of `TradingViewClient` not caught by grep (e.g., string-based dynamic import) | Low | High | Multi-pattern grep: class name, module path, dep name; `pyright` strict surfaces remaining type errors |
| `tvdatafeed` dep removal breaks transitive consumer | Low | Medium | `uv pip list` post-removal; `just test` catches import errors |
| Boot fails due to stale `TRADINGVIEW_*` env in production | Low | Medium | Settings ignores unknown env vars (Pydantic `extra="ignore"`); doc note in deployment guide (Phase 05) |
| `IRealtimeQuoteProvider` Protocol drift vs `BinanceWebSocketClient` impl | Medium | Medium | `@runtime_checkable` + DI test asserts `isinstance(client, IRealtimeQuoteProvider)` |
| Handler imports concrete `BinanceClient` (concrete-type leak) | Medium | Low | CI grep guard `grep -r "BinanceClient" packages/*/handlers/` returns 0 |
| Rollback complexity (TV code deleted) | High over time | High | Git revert merge commit restores TV; document in rollback runbook (plan.md) |

## Security considerations

- Removing `TRADINGVIEW_USERNAME/PASSWORD` reduces secret-leak surface.
- No new auth or network surface — Binance public endpoints only.

## Next steps

- Phase 04 runs production with Binance wired (this phase delivers the wire-up).
- Phase 05 documents extension point (`IDataProvider`, `IRealtimeQuoteProvider`) in `system-architecture.md`.

## Outcome

Created `infrastructure/data_provider.py` (IDataProvider ABC) + `infrastructure/realtime_quote_provider.py` (IRealtimeQuoteProvider Protocol, @runtime_checkable). DI wired BinanceClient + BinanceWebSocketClient. Deleted `infrastructure/tradingview/` folder (510 LOC) + TV tests + tvdatafeed dep. Removed TRADINGVIEW_* env vars from Settings. Final grep: 0 active TV/tvDatafeed references in codebase. 4 DI unit tests added (all pass). See [code-reviewer-260508-1352-phase-03-di-tv-removal.md](../reports/code-reviewer-260508-1352-phase-03-di-tv-removal.md).

## Unresolved questions

1. Should `IRealtimeQuoteProvider` be `Protocol` (structural) or `ABC` (nominal)? **Answer:** `Protocol` with `@runtime_checkable` — future providers (OKX) implement without inheritance.
2. Allow per-symbol provider routing later (crypto via Binance, stocks via OKX)? **Defer** — YAGNI. Re-introduce DI conditional when stocks/forex feature requested.
3. Should `pyproject.toml` removal of `tvdatafeed` bump major version? **Recommendation:** Yes — breaking change for any external consumer of `Settings.tradingview_username`. Phase 05 handles changelog + version bump.
